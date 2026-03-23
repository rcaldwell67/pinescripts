"""
paper_trader_clm_v4.py — APM v4.6 paper trading bot, CLM 30m (longs + shorts).

Run every 15 minutes at bar close via GitHub Actions (every other run is a
no-op mid-bar — harmless). Uses Alpaca paper trading API.

State persisted in docs/data/clm/v4_paper_state.json between runs:
    position          – open trade dict or null
    equity            – tracked equity (updated on each closed trade)
    cb_hwm            – circuit-breaker high-water mark
    cb_halted         – circuit-breaker active flag
    cooldown_remaining– post-loss cooldown bar count
    last_bar_ts       – last 30m bar timestamp processed (dedup)

Completed trades appended to docs/data/clm/v4_trades_paper.csv.

Run manually:
    cd /workspaces/pinescripts
    python "scripts/CLM/Adaptive Pullback Momentum v4/paper_trader_clm_v4.py"

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
    load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")
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
log = logging.getLogger("apm_v4_paper")

# ── Paths ─────────────────────────────────────────────────────────────────────
_WS         = Path(__file__).resolve().parent.parent.parent.parent
_DOCS       = _WS / "docs"
STATE_FILE  = _DOCS / "data" / "clm" / "v4_paper_state.json"
TRADES_FILE = _DOCS / "data" / "clm" / "v4_trades_paper.csv"
TRADES_COLS = [
    "entry_time", "exit_time", "direction", "entry", "exit",
    "result", "pnl_pct", "dollar_pnl", "equity",
]

# ── Credentials ───────────────────────────────────────────────────────────────
API_KEY    = (os.environ.get("ALPACA_PAPER_API_KEY")
              or os.environ.get("ALPACA_API_KEY", ""))
API_SECRET = (os.environ.get("ALPACA_PAPER_API_SECRET")
              or os.environ.get("ALPACA_API_SECRET", ""))

# ── APM v4.6 parameters (CLM 30m — matches Adaptive Pullback Momentum v4.0.pine) ──
SYMBOL          = "CLM"
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006          # 0.06% per side (matches Pine Script)
LEV_CAP         = 5.0             # max leverage cap

# Indicator params
EMA_FAST   = 21;  EMA_MID  = 50;  EMA_SLOW = 200
ADX_LEN    = 14;  RSI_LEN  = 14;  ATR_LEN  = 14;  VOL_LEN = 20
ADX_THRESH = 10
PANIC_MULT = 1.5
ATR_FLOOR  = 0.001   # 0.10% of price
PB_TOL     = 0.005   # pullback zone ± 0.50% of EMA21
VOL_MULT   = 1.0

# Entry filters (v4.6)
MIN_BODY       = 0.50    # body ≥ 0.50×ATR (was 0.15× in v4.5)
SLOPE_MIN_PCT  = 0.10    # EMA21 must move ≥ 0.10%/3bars in trade direction (NEW)

# RSI bounds
RSI_LO_L = 38;  RSI_HI_L = 68   # long entry
RSI_LO_S = 30;  RSI_HI_S = 62   # short entry

# Exit params
SL_MULT    = 1.5     # SL = entry ± ATR×1.5  (was 1.0× in v4.5)
TP_MULT    = 16.0    # TP = entry ± ATR×16.0
TRAIL_ACT  = 3.0     # trail activates after price moves ATR×3.0 in favour
TRAIL_DIST = 0.1     # trail stays ATR×0.1 from best price

# Risk / circuit-breaker
RISK_PCT   = 0.010   # 1.0% of equity risked per trade
CB_DD_PCT  = 4.0     # halt entries when equity drops 4% below HWM

# Cooldown
COOLDOWN_BARS = 13   # post-loss cooldown (bars to skip after a loss)

# Minimum bars for indicator warmup
MIN_BARS = EMA_SLOW + 60


# ── State helpers ─────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            s = json.loads(STATE_FILE.read_text())
            # ensure all keys exist (forward-compat with older state files)
            s.setdefault("position",           None)
            s.setdefault("equity",             INITIAL_CAPITAL)
            s.setdefault("cb_hwm",             INITIAL_CAPITAL)
            s.setdefault("cb_halted",          False)
            s.setdefault("cooldown_remaining", 0)
            s.setdefault("last_bar_ts",        None)
            return s
        except Exception:
            pass
    return {
        "position":           None,
        "equity":             INITIAL_CAPITAL,
        "cb_hwm":             INITIAL_CAPITAL,
        "cb_halted":          False,
        "cooldown_remaining": 0,
        "last_bar_ts":        None,
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
    """Fetch 60 days of CLM 5-min bars and resample to 30 min."""
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=60)
    req   = StockBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
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

    import pytz
    et = pytz.timezone("America/New_York")
    df.index = pd.to_datetime(df.index)
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")

    # Resample to 30-minute bars
    df30 = df.resample("30min", label="left", closed="left",
                       origin="start_day").agg(
        {"Open": "first", "High": "max", "Low": "min",
         "Close": "last", "Volume": "sum"})
    df30 = df30[df30["Volume"] > 0].dropna()
    return df30


# ── Indicators ────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["EMA_FAST"] = d["Close"].ewm(span=EMA_FAST, adjust=False).mean()
    d["EMA_MID"]  = d["Close"].ewm(span=EMA_MID,  adjust=False).mean()
    d["EMA_SLOW"] = d["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

    delta = d["Close"].diff()
    g     = delta.clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
    l_    = (-delta).clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
    d["RSI"] = 100 - 100 / (1 + g / l_.replace(0, 1e-10))

    hl  = d["High"] - d["Low"]
    hpc = (d["High"] - d["Close"].shift()).abs()
    lpc = (d["Low"]  - d["Close"].shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    d["ATR"]    = tr.ewm(alpha=1 / ATR_LEN, adjust=False).mean()
    d["ATR_BL"] = d["ATR"].rolling(60).mean()
    d["VOL_MA"] = d["Volume"].rolling(VOL_LEN).mean()

    up  = d["High"] - d["High"].shift()
    dn  = d["Low"].shift() - d["Low"]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    sp  = pd.Series(pdm, index=d.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
    sn  = pd.Series(ndm, index=d.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
    d["DI_PLUS"]  = 100 * sp / d["ATR"]
    d["DI_MINUS"] = 100 * sn / d["ATR"]
    dx = (100 * (d["DI_PLUS"] - d["DI_MINUS"]).abs()
              / (d["DI_PLUS"] + d["DI_MINUS"]).replace(0, 1e-10))
    d["ADX"] = dx.ewm(alpha=1 / ADX_LEN, adjust=False).mean()
    return d.dropna()


# ── Signal evaluation ─────────────────────────────────────────────────────────
def check_signal(df: pd.DataFrame) -> dict | None:
    """
    Evaluate APM v4.6 entry conditions on the most recently completed 30m bar.
    Returns entry dict with keys: direction, entry, sl, tp, trail_activate_px,
    trail_dist_fixed, atr — or None if no signal.
    """
    if len(df) < 5:
        return None

    bar   = df.iloc[-1]   # most recent completed bar
    prev  = df.iloc[-2]   # previous bar (pullback bar)
    bar3  = df.iloc[-4]   # 3 bars before current (EMA slope reference)

    close = float(bar["Close"])
    atr   = float(bar["ATR"])
    rsi   = float(bar["RSI"])

    # ── Regime guards (shared) ─────────────────────────────────────────────
    if float(bar["ADX"]) <= ADX_THRESH:
        log.debug("ADX %.2f ≤ %d — skip", bar["ADX"], ADX_THRESH)
        return None
    if float(bar["ATR"]) > float(bar["ATR_BL"]) * PANIC_MULT:
        log.debug("PANIC mode — skip")
        return None
    if atr / close < ATR_FLOOR:
        log.debug("ATR floor fail — skip")
        return None

    # ── Shared bar-level filters ───────────────────────────────────────────
    body_size = abs(close - float(bar["Open"])) / atr
    if body_size < MIN_BODY:
        log.debug("Body %.3f < %.3f — skip", body_size, MIN_BODY)
        return None

    vol_ok = float(bar["Volume"]) >= float(bar["VOL_MA"]) * VOL_MULT
    if not vol_ok:
        log.debug("Volume too low — skip")
        return None

    # EMA slope magnitude: % change over 3 bars
    ema_prev3 = float(bar3["EMA_FAST"])
    ema_now   = float(bar["EMA_FAST"])
    if ema_prev3 == 0:
        return None
    ema_slope_pct = (ema_now - ema_prev3) / ema_prev3 * 100

    rsi_prev = float(prev["RSI"])

    # ── Long signal ────────────────────────────────────────────────────────
    ema_bull = (float(bar["EMA_FAST"]) > float(bar["EMA_MID"]) > float(bar["EMA_SLOW"]))
    slope_up = ema_slope_pct >= SLOPE_MIN_PCT
    pb_up    = float(prev["EMA_FAST"]) * (1.0 + PB_TOL)
    long_pb  = (float(prev["Low"]) <= pb_up
                and close > float(bar["EMA_FAST"])
                and close > float(bar["Open"]))  # bullish candle
    rsi_rising = rsi > rsi_prev

    if (ema_bull and slope_up and long_pb and rsi_rising
            and RSI_LO_L <= rsi <= RSI_HI_L):
        sl  = close - atr * SL_MULT
        tp  = close + atr * TP_MULT
        tap = close + atr * TRAIL_ACT
        log.info(
            "LONG SIGNAL: entry=%.4f  SL=%.4f  TP=%.4f  slope=%.3f%%  body=%.3f",
            close, sl, tp, ema_slope_pct, body_size,
        )
        return {
            "direction":         "long",
            "entry":             close,
            "sl":                sl,
            "tp":                tp,
            "trail_activate_px": tap,
            "trail_dist_fixed":  atr * TRAIL_DIST,
            "atr":               atr,
        }

    # ── Short signal ───────────────────────────────────────────────────────
    ema_bear  = (float(bar["EMA_FAST"]) < float(bar["EMA_MID"]) < float(bar["EMA_SLOW"]))
    slope_dn  = ema_slope_pct <= -SLOPE_MIN_PCT
    pb_dn     = float(prev["EMA_FAST"]) * (1.0 - PB_TOL)
    short_pb  = (float(prev["High"]) >= pb_dn
                 and close < float(bar["EMA_FAST"])
                 and close < float(bar["Open"]))  # bearish candle
    rsi_falling = rsi < rsi_prev

    if (ema_bear and slope_dn and short_pb and rsi_falling
            and RSI_LO_S <= rsi <= RSI_HI_S):
        sl  = close + atr * SL_MULT
        tp  = close - atr * TP_MULT
        tap = close - atr * TRAIL_ACT
        log.info(
            "SHORT SIGNAL: entry=%.4f  SL=%.4f  TP=%.4f  slope=%.3f%%  body=%.3f",
            close, sl, tp, ema_slope_pct, body_size,
        )
        return {
            "direction":         "short",
            "entry":             close,
            "sl":                sl,
            "tp":                tp,
            "trail_activate_px": tap,
            "trail_dist_fixed":  atr * TRAIL_DIST,
            "atr":               atr,
        }

    log.info("No signal (slope=%.3f%%  body=%.3f  RSI=%.1f)", ema_slope_pct, body_size, rsi)
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
    """Scan recent closed orders to find the exit fill price and classify as SL/TP/Trail."""
    after_dt = datetime.fromisoformat(pos["entry_time"])
    direction = pos["direction"]
    # Exit side: long → SELL to close; short → BUY to close
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

    # Check known order IDs first
    for o in orders:
        if getattr(o.status, "value", None) == "filled" and o.filled_avg_price:
            oid = str(o.id)
            fp  = float(o.filled_avg_price)
            if oid == pos.get("tp_order_id"):
                return fp, "TP"
            if oid == pos.get("sl_order_id"):
                return fp, "SL"

    # Fallback: any filled exit-side order classified by price relative to entry
    entry = pos["entry"]
    tp    = pos["tp"]
    sl    = pos["sl"]
    for o in orders:
        if (getattr(o.status, "value", None) == "filled"
                and o.filled_avg_price
                and getattr(o.side, "value", None) == exit_side):
            fp = float(o.filled_avg_price)
            if direction == "long":
                # TP is above entry, SL is below
                if fp >= entry + (tp - entry) * 0.95:
                    return fp, "TP"
                elif fp < entry:
                    return fp, "SL"
                else:
                    return fp, "Trail"
            else:
                # TP is below entry, SL is above
                if fp <= entry - (entry - tp) * 0.95:
                    return fp, "TP"
                elif fp > entry:
                    return fp, "SL"
                else:
                    return fp, "Trail"

    return pos["sl"], "SL"   # ultimate fallback


def submit_entry(tc, direction: str, qty: int):
    side = OrderSide.BUY if direction == "long" else OrderSide.SELL
    tc.submit_order(MarketOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
        client_order_id=f"apm4_entry_{int(datetime.now(timezone.utc).timestamp())}",
    ))


def submit_sl(tc, direction: str, qty: int, sl_price: float) -> str:
    side = OrderSide.SELL if direction == "long" else OrderSide.BUY
    o = tc.submit_order(StopOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        stop_price=round(sl_price, 2),
        client_order_id=f"apm4_sl_{int(datetime.now(timezone.utc).timestamp())}",
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
        client_order_id=f"apm4_tp_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("=== APM v4.6 Paper Trader — %s 30m ===", SYMBOL)

    if not API_KEY or not API_SECRET:
        log.error(
            "Missing credentials — set ALPACA_PAPER_API_KEY and "
            "ALPACA_PAPER_API_SECRET in .env or GitHub Actions secrets."
        )
        sys.exit(1)

    data_client    = StockHistoricalDataClient(API_KEY, API_SECRET)
    trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

    # ── Market hours check ────────────────────────────────────────────────────
    try:
        clock = trading_client.get_clock()
        if not clock.is_open:
            log.info("Market is closed — nothing to do.")
            return
    except Exception as e:
        log.warning("Could not check market clock (%s) — proceeding anyway.", e)

    # ── Fetch + compute indicators ────────────────────────────────────────────
    log.info("Fetching %s 30m bars (45d)…", SYMBOL)
    df = fetch_bars(data_client)
    if df.empty or len(df) < MIN_BARS:
        log.warning("Insufficient bars (%d < %d) — skipping.", len(df), MIN_BARS)
        return

    df = compute_indicators(df)
    if df.empty:
        log.warning("Empty frame after indicators — skipping.")
        return

    # The last row is the *current open* bar — drop it; use the completed bar
    # (iloc[-2] after drop = iloc[-1] of completed bars).
    # Actually: since we fetch up to "now", the last bar may be incomplete.
    # Drop it to ensure we're always evaluating a closed bar.
    df = df.iloc[:-1]
    if df.empty:
        return

    last_bar_ts = str(df.index[-1])
    log.info("Bars: %d  last_closed=%s  close=%.4f", len(df), last_bar_ts, df["Close"].iloc[-1])

    # ── Load state ────────────────────────────────────────────────────────────
    state = load_state()
    pos   = state.get("position")

    # ── Dedup: only update counters once per new 30m bar ─────────────────────
    new_bar = (last_bar_ts != state.get("last_bar_ts"))
    if new_bar:
        # Update circuit-breaker HWM
        eq = state["equity"]
        if eq > state["cb_hwm"]:
            state["cb_hwm"] = eq

        # Check CB trigger
        cb_dd = (eq - state["cb_hwm"]) / state["cb_hwm"] * 100
        if not state["cb_halted"] and cb_dd <= -CB_DD_PCT:
            state["cb_halted"] = True
            log.warning("CIRCUIT BREAKER TRIGGERED — equity=%.2f  HWM=%.2f  DD=%.2f%%",
                        eq, state["cb_hwm"], cb_dd)
        # CB resume: when equity recovers halfway back to HWM
        resume_threshold = state["cb_hwm"] * (1.0 - CB_DD_PCT / 200.0)
        if state["cb_halted"] and eq >= resume_threshold:
            state["cb_halted"] = False
            state["cb_hwm"] = eq   # reset HWM on resume
            log.info("CIRCUIT BREAKER CLEARED — equity=%.2f", eq)

        # Decrement cooldown
        if state["cooldown_remaining"] > 0:
            state["cooldown_remaining"] -= 1
            log.info("Cooldown: %d bars remaining", state["cooldown_remaining"])

    # ── Manage open position ──────────────────────────────────────────────────
    if pos is not None:
        alpaca_pos = get_open_position(trading_client)

        if alpaca_pos is None:
            # Position was closed (SL or TP hit) — record the trade
            log.info("Position closed — recording trade.")
            exit_price, result = find_exit_fill(trading_client, pos)

            entry    = pos["entry"]
            notional = pos["notional"]
            direction = pos["direction"]

            if direction == "long":
                pnl = (exit_price - entry) / entry
            else:
                pnl = (entry - exit_price) / entry
            dp = pnl * notional - notional * COMMISSION_PCT * 2

            new_eq = state["equity"] + dp

            # Update equity in state before HWM check next run
            state["equity"] = new_eq

            # Activate post-loss cooldown
            if dp < 0 and COOLDOWN_BARS > 0:
                state["cooldown_remaining"] = COOLDOWN_BARS
                log.info("Loss — cooldown set to %d bars", COOLDOWN_BARS)

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
                "pnl_pct":    round(pnl * 100, 3),
                "dollar_pnl": round(dp, 2),
                "equity":     round(new_eq, 2),
            })
            state["position"] = None
            state["last_bar_ts"] = last_bar_ts
            save_state(state)
            log.info("Closed: %s %s  exit=%.4f  dp=%+.2f  equity=%.2f",
                     result, direction, exit_price, dp, new_eq)
            return

        # Position still open — update best price and trailing stop if new bar
        if new_bar:
            direction = pos["direction"]
            if direction == "long":
                new_best = max(pos["best"], float(df.iloc[-1]["High"]))
                pos["best"] = new_best
                if new_best >= pos["trail_activate_px"]:
                    new_sl = new_best - pos["trail_dist_fixed"]
                    if new_sl > pos["sl"]:    # trail only moves in our favour
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
                new_best = min(pos["best"], float(df.iloc[-1]["Low"]))
                pos["best"] = new_best
                if new_best <= pos["trail_activate_px"]:
                    new_sl = new_best + pos["trail_dist_fixed"]
                    if new_sl < pos["sl"]:    # trail only moves in our favour
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

        state["position"] = pos
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        log.info(
            "Position open (%s): best=%.4f  SL=%.4f  TP=%.4f  trail=%s",
            pos["direction"], pos["best"], pos["sl"], pos["tp"],
            "active" if (
                (pos["direction"] == "long"  and pos["best"] >= pos["trail_activate_px"])
                or
                (pos["direction"] == "short" and pos["best"] <= pos["trail_activate_px"])
            ) else "pending",
        )
        return

    # ── Check for untracked position (safety guard) ───────────────────────────
    if get_open_position(trading_client) is not None:
        log.warning(
            "Untracked open position in Alpaca — skipping entry to avoid doubling up."
        )
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    # ── Entry signal check ────────────────────────────────────────────────────
    if state["cb_halted"]:
        log.info("Circuit breaker active — no entry.")
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    if state["cooldown_remaining"] > 0:
        log.info("Post-loss cooldown active (%d bars) — no entry.", state["cooldown_remaining"])
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    if not new_bar:
        log.info("Same bar as last run — no new signal to check.")
        return

    signal = check_signal(df)
    if signal is None:
        log.info("No signal this bar — flat.")
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    # ── Position sizing ───────────────────────────────────────────────────────
    eq       = state["equity"]
    stop_dist = abs(signal["entry"] - signal["sl"])
    # qty = risk_amount / (stop_dist per share) — in shares integer
    qty = max(1, int(eq * RISK_PCT / stop_dist))
    # enforce leverage cap
    notional = qty * signal["entry"]
    if notional > eq * LEV_CAP:
        qty = max(1, int(eq * LEV_CAP / signal["entry"]))
        notional = qty * signal["entry"]

    direction = signal["direction"]
    log.info(
        "Entering %s: qty=%d  entry~%.4f  notional~%.2f  risk~%.2f",
        direction, qty, signal["entry"], notional, qty * stop_dist,
    )

    entry_ts    = datetime.now(timezone.utc).isoformat()
    sl_order_id = tp_order_id = "unknown"

    try:
        submit_entry(trading_client, direction, qty)
        log.info("Market %s submitted.", direction)
    except Exception as e:
        log.error("Entry order failed: %s", e)
        return

    time.sleep(2)   # let fill register before placing exit orders

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
        "trail_dist_fixed":  signal["trail_dist_fixed"],
        "sl_order_id":       sl_order_id,
        "tp_order_id":       tp_order_id,
    }
    state["last_bar_ts"] = last_bar_ts
    save_state(state)
    log.info("Position state saved.")


if __name__ == "__main__":
    main()
