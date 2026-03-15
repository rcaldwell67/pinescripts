"""
paper_trader_v5.py — APM v5.3 paper trading bot, CLM 1h (longs + shorts).

Run every 30 minutes at bar close via GitHub Actions.  Each run checks
whether a new completed 1h bar is available; if not (mid-bar check) it
only updates the trailing stop on any open position.

State persisted in docs/data/clm/v5_paper_state.json between runs:
    position      – open trade dict or null
    equity        – tracked equity (updated on each closed trade)
    last_bar_ts   – last 1h bar timestamp processed (dedup)

Completed trades appended to docs/data/clm/v5_trades_paper.csv.

Run manually:
    cd /workspaces/pinescripts/docs
    python paper_trader_v5.py

Requirements:
    pip install alpaca-py pandas numpy python-dotenv

Environment (set in .env or GitHub Actions secrets):
    ALPACA_PAPER_API_KEY
    ALPACA_PAPER_API_SECRET
"""

import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import numpy as np
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    StopOrderRequest,
    LimitOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("apm_v5_paper")

# ── Paths ─────────────────────────────────────────────────────────────────────
_DOCS       = Path(__file__).parent
STATE_FILE  = _DOCS / "data" / "clm" / "v5_paper_state.json"
TRADES_FILE = _DOCS / "data" / "clm" / "v5_trades_paper.csv"
TRADES_COLS = [
    "entry_time", "exit_time", "direction", "entry", "exit",
    "result", "pnl_pct", "dollar_pnl", "equity",
]

# ── Credentials ───────────────────────────────────────────────────────────────
API_KEY    = (os.environ.get("ALPACA_PAPER_API_KEY")
              or os.environ.get("ALPACA_API_KEY", ""))
API_SECRET = (os.environ.get("ALPACA_PAPER_API_SECRET")
              or os.environ.get("ALPACA_API_SECRET", ""))

# ── APM v5.3 parameters (CLM 1h — matches Adaptive Pullback Momentum v5.0.pine) ──
SYMBOL          = "CLM"
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006   # 0.06% per side (matches Pine Script)
LEV_CAP         = 5.0      # max leverage cap

# Indicator lengths (must match Pine Script exactly)
EMA_FAST_LEN = 21
EMA_MID_LEN  = 34
EMA_SLOW_LEN = 200
ADX_LEN      = 14
RSI_LEN      = 20
ATR_LEN      = 14
ATR_BL_LEN   = 50    # ATR baseline SMA period (50-bar, matches v5.3)
VOL_LEN      = 20

# Entry filters
ADX_THRESH = 33       # ADX must exceed this
PB_PCT     = 0.20     # pullback tolerance: prev low/high within 0.20% of EMA-fast
VOL_MULT   = 1.20     # volume ≥ 1.2× vol SMA
MIN_BODY   = 0.05     # candle body ≥ 0.05×ATR
PANIC_MULT = 1.4      # ATR > ATR_BL×1.4 → suppress entries
ATR_FLOOR  = 0.0      # no floor needed at 1h
USE_EMA_SLOPE = False # EMA slope filter disabled (sweep-optimal)

# RSI bounds
RSI_LO_L = 40;  RSI_HI_L = 70   # long entry
RSI_LO_S = 30;  RSI_HI_S = 60   # short entry

# Exit params
SL_MULT    = 0.9    # SL = entry ± ATR×0.9
TP_MULT    = 10.0   # TP = entry ± ATR×10.0  (effectively off; trail is primary)
TRAIL_ACT  = 2.0    # trail activates after price moves ATR×2.0 in favour
TRAIL_DIST = 0.5    # trail stays ATR×0.5 from best price

# Risk sizing
RISK_PCT = 0.0125   # 1.25% of equity risked per trade (v5.3)

# Minimum bars for indicator warmup
MIN_BARS = EMA_SLOW_LEN + ATR_BL_LEN + 10   # ~260 bars


# ── State helpers ─────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            s = json.loads(STATE_FILE.read_text())
            s.setdefault("position",    None)
            s.setdefault("equity",      INITIAL_CAPITAL)
            s.setdefault("last_bar_ts", None)
            return s
        except Exception:
            pass
    return {
        "position":    None,
        "equity":      INITIAL_CAPITAL,
        "last_bar_ts": None,
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def append_trade(trade: dict) -> None:
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_file = not TRADES_FILE.exists()
    with open(TRADES_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRADES_COLS)
        if new_file:
            w.writeheader()
        w.writerow({k: trade.get(k, "") for k in TRADES_COLS})
    log.info("Trade appended → %s", TRADES_FILE.name)


# ── Data fetching ─────────────────────────────────────────────────────────────
def fetch_bars(data_client) -> pd.DataFrame:
    """Fetch 90 days of CLM 30-min bars and resample to 1h for indicator warmup."""
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=90)
    req   = StockBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TimeFrame(30, TimeFrameUnit.Minute),
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    try:
        bars = data_client.get_stock_bars(req)
        df   = bars.df.reset_index()
    except Exception as e:
        log.error("fetch_bars failed: %s", e)
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df = (df[df["symbol"] == SYMBOL].copy()
            .sort_values("timestamp")
            .set_index("timestamp")
            [["open", "high", "low", "close", "volume"]]
            .rename(columns=str.title))
    df = df[df["Volume"] > 0].dropna()
    df.index = pd.to_datetime(df.index)
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")

    # Resample 30-min → 1h bars
    df1h = df.resample("1h", label="left", closed="left",
                       origin="start_day").agg(
        {"Open": "first", "High": "max", "Low": "min",
         "Close": "last", "Volume": "sum"})
    df1h = df1h[df1h["Volume"] > 0].dropna()
    return df1h


# ── Indicators ────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    d["EMA_F"]  = d["Close"].ewm(span=EMA_FAST_LEN, adjust=False).mean()
    d["EMA_M"]  = d["Close"].ewm(span=EMA_MID_LEN,  adjust=False).mean()
    d["EMA_S"]  = d["Close"].ewm(span=EMA_SLOW_LEN, adjust=False).mean()

    delta = d["Close"].diff()
    g  = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    lv = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    d["RSI"] = 100 - 100 / (1 + g / lv.replace(0, 1e-10))

    hl  = d["High"] - d["Low"]
    hpc = (d["High"] - d["Close"].shift()).abs()
    lpc = (d["Low"]  - d["Close"].shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    d["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
    d["ATR_BL"] = d["ATR"].rolling(ATR_BL_LEN).mean()
    d["VOL_MA"] = d["Volume"].rolling(VOL_LEN).mean()

    up  = d["High"].diff()
    dn  = -d["Low"].diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    sp  = pd.Series(pdm, index=d.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
    sn  = pd.Series(ndm, index=d.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
    d["DI_PLUS"]  = 100 * sp / d["ATR"].replace(0, np.nan)
    d["DI_MINUS"] = 100 * sn / d["ATR"].replace(0, np.nan)
    dx  = (100 * (d["DI_PLUS"] - d["DI_MINUS"]).abs()
               / (d["DI_PLUS"] + d["DI_MINUS"]).replace(0, 1e-10))
    d["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()

    return d.dropna()


# ── Signal evaluation ─────────────────────────────────────────────────────────
def check_signal(df: pd.DataFrame) -> dict | None:
    """
    Evaluate APM v5.3 entry conditions on the most recently completed 1h bar.
    Returns entry dict or None.
    """
    if len(df) < 5:
        return None

    bar  = df.iloc[-1]   # most recent completed bar
    prev = df.iloc[-2]   # previous bar (pullback bar)

    close = float(bar["Close"])
    atr   = float(bar["ATR"])
    atr_bl = float(bar["ATR_BL"])
    rsi   = float(bar["RSI"])

    # ── Regime guards ──────────────────────────────────────────────────────
    if float(bar["ADX"]) <= ADX_THRESH:
        log.debug("ADX %.2f ≤ %d — skip", float(bar["ADX"]), ADX_THRESH)
        return None
    if atr > atr_bl * PANIC_MULT:
        log.debug("PANIC mode (ATR %.4f > %.4f × %.1f) — skip", atr, atr_bl, PANIC_MULT)
        return None

    # ── Shared bar-level filters ────────────────────────────────────────────
    vol_ok = float(bar["Volume"]) >= float(bar["VOL_MA"]) * VOL_MULT
    if not vol_ok:
        log.debug("Volume %.2fx < %.1fx — skip",
                  float(bar["Volume"]) / float(bar["VOL_MA"]), VOL_MULT)
        return None

    body = abs(close - float(bar["Open"])) / atr
    if body < MIN_BODY:
        log.debug("Body %.3f < %.3f — skip", body, MIN_BODY)
        return None

    ema_f_now  = float(bar["EMA_F"])
    ema_m_now  = float(bar["EMA_M"])
    ema_s_now  = float(bar["EMA_S"])
    ema_f_prev = float(prev["EMA_F"])

    # Pullback tolerances based on previous bar's EMA-fast
    pb_tol_up = ema_f_prev * (1.0 + PB_PCT / 100.0)
    pb_tol_dn = ema_f_prev * (1.0 - PB_PCT / 100.0)

    stop_dist = atr * SL_MULT

    # ── Long signal ─────────────────────────────────────────────────────────
    long_pb   = (float(prev["Low"])  <= pb_tol_up
                 and close > ema_f_now
                 and close > float(bar["Open"]))   # bullish close
    ema_bull  = ema_f_now > ema_m_now and close > ema_s_now
    rsi_long  = RSI_LO_L <= rsi <= RSI_HI_L

    if long_pb and ema_bull and rsi_long:
        sl = close - stop_dist
        tp = close + atr * TP_MULT
        log.info(
            "LONG SIGNAL: entry=%.4f  sl=%.4f  tp=%.4f  "
            "atr=%.4f  adx=%.1f  rsi=%.1f  body=%.3f  vol=%.2fx",
            close, sl, tp, atr,
            float(bar["ADX"]), rsi, body,
            float(bar["Volume"]) / float(bar["VOL_MA"]),
        )
        return {
            "direction":         "long",
            "entry":             close,
            "sl":                sl,
            "tp":                tp,
            "trail_activate_px": close + atr * TRAIL_ACT,
            "trail_dist_atr":    atr * TRAIL_DIST,
            "entry_atr":         atr,
        }

    # ── Short signal ────────────────────────────────────────────────────────
    short_pb  = (float(prev["High"]) >= pb_tol_dn
                 and close < ema_f_now
                 and close < float(bar["Open"]))   # bearish close
    ema_bear  = ema_f_now < ema_m_now and close < ema_s_now
    rsi_short = RSI_LO_S <= rsi <= RSI_HI_S

    if short_pb and ema_bear and rsi_short:
        sl = close + stop_dist
        tp = close - atr * TP_MULT
        log.info(
            "SHORT SIGNAL: entry=%.4f  sl=%.4f  tp=%.4f  "
            "atr=%.4f  adx=%.1f  rsi=%.1f  body=%.3f  vol=%.2fx",
            close, sl, tp, atr,
            float(bar["ADX"]), rsi, body,
            float(bar["Volume"]) / float(bar["VOL_MA"]),
        )
        return {
            "direction":         "short",
            "entry":             close,
            "sl":                sl,
            "tp":                tp,
            "trail_activate_px": close - atr * TRAIL_ACT,
            "trail_dist_atr":    atr * TRAIL_DIST,
            "entry_atr":         atr,
        }

    log.info(
        "No signal (close=%.4f  ADX=%.1f  RSI=%.1f  body=%.3f  "
        "EMA_F=%.4f  EMA_M=%.4f  EMA_S=%.4f)",
        close, float(bar["ADX"]), rsi, body, ema_f_now, ema_m_now, ema_s_now,
    )
    return None


# ── Alpaca helpers ─────────────────────────────────────────────────────────────
def get_open_position(tc):
    try:
        return tc.get_open_position(SYMBOL)
    except Exception:
        return None


def cancel_order_safe(tc, order_id: str) -> None:
    try:
        tc.cancel_order_by_id(order_id)
        log.info("Cancelled order %s", order_id)
    except Exception as e:
        log.warning("cancel_order %s: %s", order_id, e)


def find_exit_fill(tc, pos: dict) -> tuple[float, str]:
    """Scan recent closed orders to find exit fill price and classify as SL/TP/Trail."""
    after_dt  = datetime.fromisoformat(pos["entry_time"])
    direction = pos["direction"]
    exit_side = "sell" if direction == "long" else "buy"

    try:
        orders = tc.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            symbols=[SYMBOL],
            after=after_dt,
            limit=10,
        ))
    except Exception as e:
        log.warning("get_orders failed: %s — using SL fallback", e)
        return pos["sl"], "SL"

    # Check by known order IDs first
    for o in orders:
        if getattr(o.status, "value", None) == "filled" and o.filled_avg_price:
            oid = str(o.id)
            fp  = float(o.filled_avg_price)
            if oid == pos.get("tp_order_id"):
                return fp, "TP"
            if oid == pos.get("sl_order_id"):
                return fp, "SL"

    # Fallback: classify by price vs entry/tp/sl
    entry = pos["entry"]
    tp    = pos["tp"]
    for o in orders:
        if (getattr(o.status, "value", None) == "filled"
                and o.filled_avg_price
                and getattr(o.side, "value", None) == exit_side):
            fp = float(o.filled_avg_price)
            if direction == "long":
                if fp >= entry + (tp - entry) * 0.95:
                    return fp, "TP"
                elif fp < entry:
                    return fp, "SL"
                else:
                    return fp, "Trail"
            else:
                if fp <= entry - (entry - tp) * 0.95:
                    return fp, "TP"
                elif fp > entry:
                    return fp, "SL"
                else:
                    return fp, "Trail"

    return pos["sl"], "SL"   # ultimate fallback


def submit_entry(tc, direction: str, qty: int) -> None:
    side = OrderSide.BUY if direction == "long" else OrderSide.SELL
    tc.submit_order(MarketOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
        client_order_id=f"apm5_entry_{int(datetime.now(timezone.utc).timestamp())}",
    ))


def submit_sl(tc, direction: str, qty: int, sl_price: float) -> str:
    side = OrderSide.SELL if direction == "long" else OrderSide.BUY
    o = tc.submit_order(StopOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        stop_price=round(sl_price, 2),
        client_order_id=f"apm5_sl_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


def submit_tp(tc, direction: str, qty: int, tp_price: float) -> str:
    side = OrderSide.SELL if direction == "long" else OrderSide.BUY
    o = tc.submit_order(LimitOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        limit_price=round(tp_price, 2),
        client_order_id=f"apm5_tp_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("=== APM v5.3 Paper Trader — %s 1h ===", SYMBOL)

    if not API_KEY or not API_SECRET:
        log.error(
            "Missing credentials — set ALPACA_PAPER_API_KEY and "
            "ALPACA_PAPER_API_SECRET in .env or GitHub Actions secrets."
        )
        sys.exit(1)

    data_client    = StockHistoricalDataClient(API_KEY, API_SECRET)
    trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

    # ── Market hours check ─────────────────────────────────────────────────────
    try:
        clock = trading_client.get_clock()
        if not clock.is_open:
            log.info("Market is closed — nothing to do.")
            return
    except Exception as e:
        log.warning("Could not check market clock (%s) — proceeding anyway.", e)

    # ── Fetch + compute indicators ─────────────────────────────────────────────
    log.info("Fetching %s 1h bars (90d)…", SYMBOL)
    df = fetch_bars(data_client)
    if df.empty or len(df) < MIN_BARS:
        log.warning("Insufficient bars (%d < %d) — skipping.", len(df), MIN_BARS)
        return

    df = compute_indicators(df)
    if df.empty:
        log.warning("Empty frame after indicators — skipping.")
        return

    # Drop the current (possibly incomplete) bar; evaluate only completed bars.
    df = df.iloc[:-1]
    if df.empty:
        return

    last_bar_ts = str(df.index[-1])
    log.info("Bars: %d  last_closed=%s  close=%.4f",
             len(df), last_bar_ts, df["Close"].iloc[-1])

    # ── Load state ─────────────────────────────────────────────────────────────
    state   = load_state()
    pos     = state.get("position")
    new_bar = (last_bar_ts != state.get("last_bar_ts"))

    # ── Manage open position ───────────────────────────────────────────────────
    if pos is not None:
        alpaca_pos = get_open_position(trading_client)

        if alpaca_pos is None:
            # Position was closed server-side (SL or TP hit) — record the trade
            log.info("Position closed externally — recording trade.")
            exit_price, result = find_exit_fill(trading_client, pos)

            entry     = pos["entry"]
            notional  = pos["notional"]
            direction = pos["direction"]

            if direction == "long":
                pnl_pct = (exit_price - entry) / entry
            else:
                pnl_pct = (entry - exit_price) / entry
            dollar_pnl = pnl_pct * notional - notional * COMMISSION_PCT * 2

            state["equity"] += dollar_pnl

            # Cancel any remaining exit orders
            for oid in (pos.get("sl_order_id"), pos.get("tp_order_id")):
                if oid and oid != "unknown":
                    cancel_order_safe(trading_client, oid)

            append_trade({
                "entry_time": pos["entry_time"],
                "exit_time":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "direction":  direction,
                "entry":      round(entry, 4),
                "exit":       round(exit_price, 4),
                "result":     result,
                "pnl_pct":    round(pnl_pct * 100, 3),
                "dollar_pnl": round(dollar_pnl, 2),
                "equity":     round(state["equity"], 2),
            })
            state["position"]    = None
            state["last_bar_ts"] = last_bar_ts
            save_state(state)
            log.info(
                "Closed: %s %s  exit=%.4f  pnl=%+.2f  equity=%.2f",
                result, direction, exit_price, dollar_pnl, state["equity"],
            )
            return

        # Position still open — update trailing stop on new completed bar
        if new_bar:
            direction   = pos["direction"]
            entry_atr   = pos["entry_atr"]          # ATR at entry time
            trail_dist  = entry_atr * TRAIL_DIST     # fixed trail cushion

            bar_close = float(df.iloc[-1]["Close"])
            bar_high  = float(df.iloc[-1]["High"])
            bar_low   = float(df.iloc[-1]["Low"])

            if direction == "long":
                new_best = max(pos["best"], bar_high)
                if new_best != pos["best"]:
                    log.info("Long best updated: %.4f → %.4f", pos["best"], new_best)
                pos["best"] = new_best
                if new_best >= pos["trail_activate_px"]:
                    new_sl = new_best - trail_dist
                    if new_sl > pos["sl"]:
                        log.info("Trail(L): SL %.4f → %.4f", pos["sl"], new_sl)
                        pos["sl"] = new_sl
                        if pos.get("sl_order_id") not in (None, "unknown"):
                            cancel_order_safe(trading_client, pos["sl_order_id"])
                        try:
                            qty = abs(int(float(alpaca_pos.qty)))
                            new_id = submit_sl(trading_client, "long", qty, new_sl)
                            pos["sl_order_id"] = new_id
                            log.info("New SL order: id=%s  price=%.4f", new_id, new_sl)
                        except Exception as e:
                            log.error("SL update failed: %s", e)
            else:
                new_best = min(pos["best"], bar_low)
                if new_best != pos["best"]:
                    log.info("Short best updated: %.4f → %.4f", pos["best"], new_best)
                pos["best"] = new_best
                if new_best <= pos["trail_activate_px"]:
                    new_sl = new_best + trail_dist
                    if new_sl < pos["sl"]:
                        log.info("Trail(S): SL %.4f → %.4f", pos["sl"], new_sl)
                        pos["sl"] = new_sl
                        if pos.get("sl_order_id") not in (None, "unknown"):
                            cancel_order_safe(trading_client, pos["sl_order_id"])
                        try:
                            qty = abs(int(float(alpaca_pos.qty)))
                            new_id = submit_sl(trading_client, "short", qty, new_sl)
                            pos["sl_order_id"] = new_id
                            log.info("New SL order: id=%s  price=%.4f", new_id, new_sl)
                        except Exception as e:
                            log.error("SL update failed: %s", e)

        state["position"]    = pos
        state["last_bar_ts"] = last_bar_ts
        save_state(state)

        trail_live = (
            (pos["direction"] == "long"  and pos["best"] >= pos["trail_activate_px"])
            or (pos["direction"] == "short" and pos["best"] <= pos["trail_activate_px"])
        )
        log.info(
            "Position open (%s): best=%.4f  SL=%.4f  TP=%.4f  trail=%s",
            pos["direction"], pos["best"], pos["sl"], pos["tp"],
            "active" if trail_live else "pending",
        )
        return

    # ── Check for untracked position (safety guard) ────────────────────────────
    if get_open_position(trading_client) is not None:
        log.warning(
            "Untracked open position in Alpaca — skipping entry to avoid doubling up."
        )
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    # ── Entry signal (only evaluate on new completed bar) ─────────────────────
    if not new_bar:
        log.info("Same bar as last run — no new signal to check.")
        return

    signal = check_signal(df)
    if signal is None:
        log.info("No signal this bar — flat.")
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    # ── Position sizing ────────────────────────────────────────────────────────
    eq        = state["equity"]
    stop_dist = abs(signal["entry"] - signal["sl"])
    qty       = max(1, int(eq * RISK_PCT / stop_dist))
    notional  = qty * signal["entry"]
    # Enforce leverage cap
    if notional > eq * LEV_CAP:
        qty      = max(1, int(eq * LEV_CAP / signal["entry"]))
        notional = qty * signal["entry"]

    direction = signal["direction"]
    log.info(
        "Entering %s: qty=%d  entry~%.4f  notional~$%.2f  stop_dist=%.4f  risk~$%.2f",
        direction, qty, signal["entry"], notional,
        stop_dist, qty * stop_dist,
    )

    entry_ts    = datetime.now(timezone.utc).isoformat()
    sl_order_id = tp_order_id = "unknown"

    try:
        submit_entry(trading_client, direction, qty)
        log.info("Market %s order submitted.", direction)
    except Exception as e:
        log.error("Entry order failed: %s", e)
        return

    time.sleep(2)   # allow fill to register before placing exit orders

    try:
        sl_order_id = submit_sl(trading_client, direction, qty, signal["sl"])
        log.info("SL order: id=%s  price=%.4f", sl_order_id, signal["sl"])
    except Exception as e:
        log.error("SL order failed: %s", e)

    try:
        tp_order_id = submit_tp(trading_client, direction, qty, signal["tp"])
        log.info("TP order: id=%s  price=%.4f", tp_order_id, signal["tp"])
    except Exception as e:
        log.error("TP order failed: %s", e)

    state["position"] = {
        "entry_time":        entry_ts,
        "direction":         direction,
        "entry":             signal["entry"],
        "sl":                signal["sl"],
        "tp":                signal["tp"],
        "best":              signal["entry"],
        "notional":          notional,
        "trail_activate_px": signal["trail_activate_px"],
        "entry_atr":         signal["entry_atr"],   # stored for trail_dist recomputation
        "sl_order_id":       sl_order_id,
        "tp_order_id":       tp_order_id,
    }
    state["last_bar_ts"] = last_bar_ts
    save_state(state)
    log.info("Position state saved.")


if __name__ == "__main__":
    main()
