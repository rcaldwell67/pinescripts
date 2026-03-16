"""
paper_trader_clm_v2.py — APM v2.5 paper trading bot, CLM 10m shorts.

Run every 15 minutes at bar close via GitHub Actions.
Uses Alpaca paper trading API.

★ Key differences from paper_trader_v3.py:
  - CLM 10m bars (Alpaca 5m IEX → resampled to 10m)
  - v2.5 signal params: ADX≥17, PB=0.30%, VOL≥0.7×, SL=2×ATR,
    TP=9×ATR, trail_act=3.5, trail_dist=0.2, risk=2.5%, max_bars=20
  - Session-gated entries: 9:00–14:00 ET only
  - Momentum filter: close must be below close 5 bars ago
  - MAX_BARS exit: position closed via market order after 20 x 10m bars

State persisted in docs/data/clm/v2_paper_state.json.
Completed trades appended to docs/data/clm/v2_trades_paper.csv.

Run manually:
    cd /workspaces/pinescripts
    python "scripts/CLM/Adaptive Pullback Momentum v2/paper_trader_clm_v2.py"

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
from zoneinfo import ZoneInfo

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
log = logging.getLogger("apm_v2_paper")

# ── Paths ─────────────────────────────────────────────────────────────────────
_WS         = Path(__file__).resolve().parent.parent.parent.parent
_DOCS       = _WS / "docs"
STATE_FILE  = _DOCS / "data" / "clm" / "v2_paper_state.json"
TRADES_FILE = _DOCS / "data" / "clm" / "v2_trades_paper.csv"
TRADES_COLS = [
    "entry_time", "exit_time", "direction", "entry", "exit",
    "result", "pnl_pct", "dollar_pnl", "equity",
]

# ── Credentials ───────────────────────────────────────────────────────────────
API_KEY    = (os.environ.get("ALPACA_PAPER_API_KEY")
              or os.environ.get("ALPACA_API_KEY", ""))
API_SECRET = (os.environ.get("ALPACA_PAPER_API_SECRET")
              or os.environ.get("ALPACA_API_SECRET", ""))

# ── APM v2.5 parameters (CLM 10m — matches sweep_stage5 backtest exactly) ────
SYMBOL     = "CLM"
_ET        = ZoneInfo("America/New_York")

EMA_FAST   = 21;  EMA_MID  = 50;  EMA_SLOW = 200
ADX_LEN    = 14;  RSI_LEN  = 14;  ATR_LEN  = 14;  VOL_LEN = 20
ATR_BL_LEN = 60
MOMENTUM_BARS   = 5
ADX_THRESH      = 17
PB_PCT          = 0.30    # pullback tolerance %
VOL_MULT        = 0.7
MIN_BODY        = 0.20
ATR_FLOOR       = 0.001   # ATR/price must exceed 0.1%
PANIC_MULT      = 1.5
RSI_LO_S        = 32;  RSI_HI_S = 58
SL_MULT         = 2.0
TP_MULT         = 9.0
TRAIL_ACT       = 3.5
TRAIL_DIST      = 0.2
MAX_BARS        = 20
RISK_PCT        = 0.025   # 2.5% equity per trade
COMMISSION_PCT  = 0.0006
INITIAL_CAPITAL = 10_000.0
SESSION_START_ET = 9      # entries only 09:00–14:00 ET
SESSION_END_ET   = 14

MIN_BARS = EMA_SLOW + ATR_BL_LEN + 10  # warmup bars needed


# ── State helpers ─────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"position": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def last_equity() -> float:
    if not TRADES_FILE.exists():
        return INITIAL_CAPITAL
    try:
        with open(TRADES_FILE) as f:
            rows = list(csv.DictReader(f))
        return float(rows[-1]["equity"]) if rows else INITIAL_CAPITAL
    except Exception:
        return INITIAL_CAPITAL


def append_trade(trade: dict) -> None:
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_file = not TRADES_FILE.exists()
    with open(TRADES_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRADES_COLS)
        if new_file:
            w.writeheader()
        w.writerow({k: trade.get(k, "") for k in TRADES_COLS})
    log.info("Trade appended → %s", TRADES_FILE.name)


# ── Data fetching (5m → resample to 10m) ─────────────────────────────────────
def fetch_bars(data_client) -> pd.DataFrame:
    """Fetch 30 days of CLM 5m bars from Alpaca IEX and resample to 10m."""
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    req   = StockBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    try:
        bars = data_client.get_stock_bars(req)
        raw  = bars.df.reset_index()
    except Exception as e:
        log.error("fetch_bars failed: %s", e)
        return pd.DataFrame()
    if raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(0)
    raw = (raw[raw["symbol"] == SYMBOL].copy()
             .rename(columns={"timestamp": "time"})
             .set_index("time")
             [["open", "high", "low", "close", "volume"]]
             .rename(columns=str.title))
    raw.index = pd.to_datetime(raw.index)
    if raw.index.tzinfo is None:
        raw.index = raw.index.tz_localize("UTC")
    raw = raw[raw["Volume"] > 0].dropna()

    # Resample 5m → 10m, aligned to session start
    raw_et = raw.copy()
    raw_et.index = raw_et.index.tz_convert(_ET)
    df = raw_et.resample(
        "10min", label="left", closed="left", origin="start_day"
    ).agg({"Open": "first", "High": "max", "Low": "min",
           "Close": "last", "Volume": "sum"})
    df = df[df["Volume"] > 0].dropna()
    log.info("10m bars: %d  (%s … %s)", len(df), df.index[0], df.index[-1])
    return df


# ── Indicators ────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["EMA_FAST"] = d["Close"].ewm(span=EMA_FAST, adjust=False).mean()
    d["EMA_MID"]  = d["Close"].ewm(span=EMA_MID,  adjust=False).mean()
    d["EMA_SLOW"] = d["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

    delta = d["Close"].diff()
    g     = delta.clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
    l     = (-delta).clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
    d["RSI"] = 100 - 100 / (1 + g / l.replace(0, 1e-10))

    hl  = d["High"] - d["Low"]
    hpc = (d["High"] - d["Close"].shift()).abs()
    lpc = (d["Low"]  - d["Close"].shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    d["ATR"]    = tr.ewm(alpha=1 / ATR_LEN, adjust=False).mean()
    d["ATR_BL"] = d["ATR"].rolling(ATR_BL_LEN).mean()
    d["VOL_MA"] = d["Volume"].rolling(VOL_LEN).mean()

    up  = d["High"] - d["High"].shift()
    dn  = d["Low"].shift() - d["Low"]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    sp  = pd.Series(pdm, index=d.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
    sn  = pd.Series(ndm, index=d.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
    d["DI_PLUS"]  = 100 * sp / d["ATR"].replace(0, 1e-10)
    d["DI_MINUS"] = 100 * sn / d["ATR"].replace(0, 1e-10)
    dx = (100 * (d["DI_PLUS"] - d["DI_MINUS"]).abs()
              / (d["DI_PLUS"] + d["DI_MINUS"]).replace(0, 1e-10))
    d["ADX"] = dx.ewm(alpha=1 / ADX_LEN, adjust=False).mean()
    return d.dropna()


# ── Count bars since entry ────────────────────────────────────────────────────
def bars_since_entry(df: pd.DataFrame, entry_bar_time: str) -> int:
    """
    Count how many completed 10m bars exist in df from entry_bar_time onward
    (inclusive of entry bar itself). Returns 0 if entry bar not found.
    """
    try:
        entry_ts = pd.Timestamp(entry_bar_time).tz_convert(_ET)
        # Find index position of entry bar (or first bar after it)
        idx_arr = df.index
        pos_arr = idx_arr.searchsorted(entry_ts, side="left")
        if pos_arr >= len(idx_arr):
            return 0
        return len(idx_arr) - pos_arr
    except Exception as e:
        log.warning("bars_since_entry error: %s", e)
        return 0


# ── Signal evaluation ─────────────────────────────────────────────────────────
def check_short_signal(df: pd.DataFrame) -> dict | None:
    """
    Evaluate APM v2.5 short entry conditions on the most recent completed bar.
    iloc[-1] = recovery bar (entry candidate)
    iloc[-2] = pullback bar
    Returns parameters dict if signal fires, else None.
    """
    if len(df) < MOMENTUM_BARS + 2:
        return None

    bar  = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(bar["Close"])
    atr   = float(bar["ATR"])

    # Session gate: only enter 09:00–14:00 ET
    bar_et = bar.name.astimezone(_ET)
    if not (SESSION_START_ET <= bar_et.hour < SESSION_END_ET):
        log.debug("Outside session (hour=%d) — skip", bar_et.hour)
        return None

    # Regime guards
    if float(bar["ADX"]) <= ADX_THRESH:
        log.debug("ADX %.2f ≤ %d — skip", bar["ADX"], ADX_THRESH)
        return None
    if float(bar["ATR"]) > float(bar["ATR_BL"]) * PANIC_MULT:
        log.debug("PANIC mode — skip")
        return None

    # Bearish EMA stack
    if not (float(bar["EMA_FAST"]) < float(bar["EMA_MID"]) < float(bar["EMA_SLOW"])):
        log.debug("EMA stack not bearish — skip")
        return None

    # Pullback: prev bar high ≥ EMA_FAST_prev × (1 − PB_PCT%)
    pb_tol = float(prev["EMA_FAST"]) * (1.0 - PB_PCT / 100.0)
    if float(prev["High"]) < pb_tol:
        log.debug("No pullback (prev high %.4f < %.4f) — skip", prev["High"], pb_tol)
        return None

    # Recovery bar: close < EMA_FAST and bearish candle
    if not (close < float(bar["EMA_FAST"]) and close < float(bar["Open"])):
        log.debug("Recovery bar conditions not met — skip")
        return None

    # Min body (doji rejection)
    body = abs(close - float(bar["Open"])) / (atr or 1e-10)
    if body < MIN_BODY:
        log.debug("Body %.3f < %.3f — skip", body, MIN_BODY)
        return None

    # RSI falling + in range
    if float(bar["RSI"]) >= float(prev["RSI"]):
        log.debug("RSI not falling — skip")
        return None
    if not (RSI_LO_S <= float(bar["RSI"]) <= RSI_HI_S):
        log.debug("RSI %.2f out of [%d,%d] — skip", bar["RSI"], RSI_LO_S, RSI_HI_S)
        return None

    # Volume
    if float(bar["Volume"]) < float(bar["VOL_MA"]) * VOL_MULT:
        log.debug("Volume too low — skip")
        return None

    # ATR floor
    if atr / close < ATR_FLOOR:
        log.debug("ATR floor fail — skip")
        return None

    # Momentum: close below close 5 bars ago
    if close >= float(df.iloc[-(MOMENTUM_BARS + 1)]["Close"]):
        log.debug("Momentum filter fail (close not below 5-bar-ago) — skip")
        return None

    # ── Signal fires! ──────────────────────────────────────────────────────
    sd = atr * SL_MULT
    signal = {
        "entry":             close,
        "sl":                close + sd,
        "tp":                close - atr * TP_MULT,
        "trail_activate_px": close - atr * TRAIL_ACT,
        "trail_dist_fixed":  atr * TRAIL_DIST,
        "atr":               atr,
        "entry_bar_time":    bar.name.isoformat(),
    }
    log.info(
        "SHORT SIGNAL: entry=%.4f  SL=%.4f  TP=%.4f  ATR=%.4f",
        signal["entry"], signal["sl"], signal["tp"], signal["atr"],
    )
    return signal


# ── Alpaca helpers ────────────────────────────────────────────────────────────
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
    """Scan recent closed orders to find the exit fill for a position."""
    after_dt = datetime.fromisoformat(pos["entry_time"])
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

    # Check our known order IDs first
    for o in orders:
        if getattr(o.status, "value", None) == "filled" and o.filled_avg_price:
            oid = str(o.id)
            fp  = float(o.filled_avg_price)
            if oid == pos.get("tp_order_id"):
                return fp, "TP"
            if oid == pos.get("sl_order_id"):
                return fp, "SL"

    # Fallback: any filled buy-to-cover order, classify by price
    for o in orders:
        if (getattr(o.status, "value", None) == "filled"
                and o.filled_avg_price
                and getattr(o.side, "value", None) == "buy"):
            fp = float(o.filled_avg_price)
            if fp <= pos["tp"] * 1.005:
                return fp, "TP"
            elif fp < pos["entry"]:
                return fp, "Trail"
            else:
                return fp, "SL"

    return pos["sl"], "SL"


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not API_KEY or not API_SECRET:
        log.error("ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET not set.")
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
    log.info("Fetching %s 5m bars → resample to 10m (30d)…", SYMBOL)
    df = fetch_bars(data_client)
    if df.empty or len(df) < MIN_BARS:
        log.warning("Insufficient bars (%d < %d) — skipping.", len(df), MIN_BARS)
        return

    df = compute_indicators(df)
    if df.empty:
        log.warning("Empty frame after indicators — skipping.")
        return

    log.info(
        "Bars: %d  last=%s  close=%.4f  ADX=%.2f",
        len(df), df.index[-1], df["Close"].iloc[-1], df["ADX"].iloc[-1],
    )

    # ── Manage open position ──────────────────────────────────────────────────
    state = load_state()
    pos   = state.get("position")

    if pos is not None:
        alpaca_pos = get_open_position(trading_client)

        if alpaca_pos is None:
            # Position was closed externally (SL/TP/Trail hit)
            log.info("Position closed externally — recording trade.")
            exit_price, result = find_exit_fill(trading_client, pos)

            entry    = pos["entry"]
            notional = pos["notional"]
            pnl      = (entry - exit_price) / entry
            dp       = pnl * notional - notional * COMMISSION_PCT * 2
            new_eq   = last_equity() + dp

            for oid in (pos.get("sl_order_id"), pos.get("tp_order_id")):
                if oid and oid != "unknown":
                    cancel_order_safe(trading_client, oid)

            append_trade({
                "entry_time": pos["entry_time"],
                "exit_time":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "direction":  "short",
                "entry":      round(entry, 4),
                "exit":       round(exit_price, 4),
                "result":     result,
                "pnl_pct":    round(pnl * 100, 3),
                "dollar_pnl": round(dp, 2),
                "equity":     round(new_eq, 2),
            })
            state["position"] = None
            save_state(state)
            log.info("Closed: %s  exit=%.4f  dp=%+.2f  equity=%.2f",
                     result, exit_price, dp, new_eq)
            return

        # ── MAX_BARS check ────────────────────────────────────────────────────
        nbars = bars_since_entry(df, pos.get("entry_bar_time", pos["entry_time"]))
        log.info("Bars in trade: %d / %d", nbars, MAX_BARS)

        if nbars >= MAX_BARS:
            log.info("MAX_BARS (%d) reached — exiting at market.", MAX_BARS)
            qty = abs(float(alpaca_pos.qty))
            try:
                trading_client.submit_order(MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                    client_order_id=f"apm2_mb_{int(datetime.now(timezone.utc).timestamp())}",
                ))
                log.info("MB market order submitted.")
            except Exception as e:
                log.error("MB exit order failed: %s", e)
                return

            time.sleep(2)
            # Cancel outstanding limit/stop orders
            for oid in (pos.get("sl_order_id"), pos.get("tp_order_id")):
                if oid and oid != "unknown":
                    cancel_order_safe(trading_client, oid)

            # Record at current close price as approximation
            exit_price = float(df["Close"].iloc[-1])
            entry      = pos["entry"]
            notional   = pos["notional"]
            pnl        = (entry - exit_price) / entry
            dp         = pnl * notional - notional * COMMISSION_PCT * 2
            new_eq     = last_equity() + dp

            append_trade({
                "entry_time": pos["entry_time"],
                "exit_time":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "direction":  "short",
                "entry":      round(entry, 4),
                "exit":       round(exit_price, 4),
                "result":     "MB",
                "pnl_pct":    round(pnl * 100, 3),
                "dollar_pnl": round(dp, 2),
                "equity":     round(new_eq, 2),
            })
            state["position"] = None
            save_state(state)
            log.info("MB exit: exit~%.4f  dp=%+.2f  equity=%.2f",
                     exit_price, dp, new_eq)
            return

        # ── Trailing stop update ──────────────────────────────────────────────
        current_low = float(df.iloc[-1]["Low"])
        new_best    = min(pos["best"], current_low)
        if new_best < pos["best"]:
            pos["best"] = new_best
            log.info("Best price updated: %.4f", new_best)

        if new_best <= pos["trail_activate_px"]:
            new_sl = new_best + pos["trail_dist_fixed"]
            if new_sl < pos["sl"]:
                log.info("Trail: SL %.4f → %.4f", pos["sl"], new_sl)
                pos["sl"] = new_sl
                if pos.get("sl_order_id") and pos["sl_order_id"] != "unknown":
                    cancel_order_safe(trading_client, pos["sl_order_id"])
                qty = abs(float(alpaca_pos.qty))
                try:
                    new_sl_ord = trading_client.submit_order(StopOrderRequest(
                        symbol=SYMBOL,
                        qty=qty,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.GTC,
                        stop_price=round(new_sl, 2),
                        client_order_id=f"apm2_sl_{int(datetime.now(timezone.utc).timestamp())}",
                    ))
                    pos["sl_order_id"] = str(new_sl_ord.id)
                    log.info("New SL order: id=%s  price=%.4f",
                             pos["sl_order_id"], new_sl)
                except Exception as e:
                    log.error("Failed to place updated SL order: %s", e)

        state["position"] = pos
        save_state(state)
        log.info(
            "Position open: bars=%d  best=%.4f  SL=%.4f  TP=%.4f  trailing=%s",
            nbars, pos["best"], pos["sl"], pos["tp"],
            "active" if new_best <= pos["trail_activate_px"] else "pending",
        )
        return

    # ── Check for untracked position (safety guard) ───────────────────────────
    if get_open_position(trading_client) is not None:
        log.warning(
            "Untracked open position in Alpaca — skipping entry to avoid doubling up."
        )
        return

    # ── Entry signal check ────────────────────────────────────────────────────
    signal = check_short_signal(df)
    if signal is None:
        log.info("No signal — flat, nothing to do.")
        return

    # Position sizing: risk RISK_PCT of tracked equity
    tracked_equity = last_equity()
    stop_dist = signal["sl"] - signal["entry"]
    qty       = max(1, int(tracked_equity * RISK_PCT / stop_dist))
    notional  = qty * signal["entry"]
    log.info(
        "Entering short: qty=%d  entry~%.4f  notional~%.2f  risk~%.2f",
        qty, signal["entry"], notional, qty * stop_dist,
    )

    entry_ts    = datetime.now(timezone.utc).isoformat()
    sl_order_id = tp_order_id = "unknown"

    # Market short order
    try:
        trading_client.submit_order(MarketOrderRequest(
            symbol=SYMBOL,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=f"apm2_entry_{int(datetime.now(timezone.utc).timestamp())}",
        ))
        log.info("Market short submitted.")
    except Exception as e:
        log.error("Entry order failed: %s", e)
        return

    time.sleep(2)

    # Stop loss order
    try:
        sl_ord = trading_client.submit_order(StopOrderRequest(
            symbol=SYMBOL,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            stop_price=round(signal["sl"], 2),
            client_order_id=f"apm2_sl_{int(datetime.now(timezone.utc).timestamp())}",
        ))
        sl_order_id = str(sl_ord.id)
        log.info("SL order: id=%s  price=%.4f", sl_order_id, signal["sl"])
    except Exception as e:
        log.error("SL order failed: %s", e)

    # Take-profit limit order
    try:
        tp_ord = trading_client.submit_order(LimitOrderRequest(
            symbol=SYMBOL,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            limit_price=round(signal["tp"], 2),
            client_order_id=f"apm2_tp_{int(datetime.now(timezone.utc).timestamp())}",
        ))
        tp_order_id = str(tp_ord.id)
        log.info("TP order: id=%s  price=%.4f", tp_order_id, signal["tp"])
    except Exception as e:
        log.error("TP order failed: %s", e)

    state["position"] = {
        "entry_time":        entry_ts,
        "entry_bar_time":    signal["entry_bar_time"],
        "direction":         "short",
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
    save_state(state)
    log.info("Position state saved.")


if __name__ == "__main__":
    main()
