"""
paper_trader_btcusd_v2.py — APM v2.0 paper trading bot, BTC/USD 10m (shorts only).

Run every 10 minutes via GitHub Actions (or cron). Fetches 5m bars from Alpaca
and resamples to 10m. Evaluates APM v2.0 short entry conditions (session filter,
momentum) and manages any open short position (trailing stop, MaxBars time-exit).

Strategy parameters (Pine v2.0 10m, current +20% calibration):
    ADX=15 | PB=0.30% | SL×2.0 | TP×6.0 | TRAIL_ACT=2.5× | TRAIL_DIST=0.1×
    MAX_BARS=30 | ATR_FLOOR=0.10% | PANIC=1.5× | VOL=0.7× | MIN_BODY=0.15×
    MOMENTUM=5 bars | SESSION 9–14 ET | COOLDOWN after 2 SL

State:  docs/data/btcusd/v2_paper_state.json
Trades: docs/data/btcusd/v2_trades_paper.csv

Run manually:
    cd /workspaces/pinescripts
    python "scripts/BTCUSD/Adaptive Pullback Momentum v2/paper_trader_btcusd_v2.py"

Requirements:
    pip install alpaca-py pandas numpy python-dotenv pytz

Environment:
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

import pytz

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")
except ImportError:
    pass

import numpy as np
import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
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
log = logging.getLogger("apm_btcusd_v2")

# ── Paths ─────────────────────────────────────────────────────────────────────
_WS         = Path(__file__).resolve().parent.parent.parent.parent
STATE_FILE  = _WS / "docs" / "data" / "btcusd" / "v2_paper_state.json"
TRADES_FILE = _WS / "docs" / "data" / "btcusd" / "v2_trades_paper.csv"
TRADES_COLS = [
    "entry_time", "exit_time", "direction", "entry", "exit",
    "exit_reason", "bars_held", "pnl_pct", "dollar_pnl", "equity",
]

# ── Credentials ───────────────────────────────────────────────────────────────
API_KEY    = (os.environ.get("ALPACA_PAPER_API_KEY")
              or os.environ.get("ALPACA_API_KEY", ""))
API_SECRET = (os.environ.get("ALPACA_PAPER_API_SECRET")
              or os.environ.get("ALPACA_API_SECRET", ""))

# ── APM v2.0 parameters (BTC/USD 10m — current +20% calibration) ─────────────
SYMBOL          = "BTC/USD"
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
RISK_PCT        = 0.03
LEV_CAP         = 5.0

EMA_FAST_LEN = 21
EMA_MID_LEN  = 50
EMA_SLOW_LEN = 200
ADX_LEN      = 14
RSI_LEN      = 14
ATR_LEN      = 14
ATR_BL_LEN   = 60
VOL_LEN      = 20

ADX_THRESH = 15
PB_PCT     = 0.30
VOL_MULT   = 0.7
MIN_BODY   = 0.15
ATR_FLOOR  = 0.0010
PANIC_MULT = 1.5

RSI_LO_L = 42; RSI_HI_L = 68
RSI_LO_S = 32; RSI_HI_S = 58

SL_MULT    = 2.0
TP_MULT    = 6.0
TRAIL_ACT  = 2.5
TRAIL_DIST = 0.1
MAX_BARS   = 30

MOMENTUM_BARS        = 5   # close < close[5] for shorts
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1

SESSION_START_ET = 9
SESSION_END_ET   = 14

TRADE_LONGS  = False
TRADE_SHORTS = True

MIN_BARS = EMA_SLOW_LEN + ATR_BL_LEN + 10

_ET = pytz.timezone("America/New_York")


# ── State helpers ─────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            s = json.loads(STATE_FILE.read_text())
            s.setdefault("position",      None)
            s.setdefault("equity",        INITIAL_CAPITAL)
            s.setdefault("last_bar_ts",   None)
            s.setdefault("consec_losses", 0)
            s.setdefault("cooldown_bars", 0)
            return s
        except Exception:
            pass
    return {
        "position":      None,
        "equity":        INITIAL_CAPITAL,
        "last_bar_ts":   None,
        "consec_losses": 0,
        "cooldown_bars": 0,
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


# ── Data fetching ──────────────────────────────────────────────────────────────
def fetch_bars(data_client) -> pd.DataFrame:
    """Fetch 60 days of BTC/USD 5m bars and resample to 10m."""
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=60)
    req   = CryptoBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=start,
        end=end,
    )
    try:
        bars = data_client.get_crypto_bars(req)
        df5  = bars.df.reset_index()
    except Exception as e:
        log.error("fetch_bars failed: %s", e)
        return pd.DataFrame()
    if df5.empty:
        return pd.DataFrame()

    df5 = (df5[df5["symbol"] == SYMBOL].copy()
             .sort_values("timestamp")
             .set_index("timestamp")
             [["open", "high", "low", "close", "volume"]]
             .rename(columns=str.title))
    df5 = df5[df5["Volume"] > 0].dropna()
    df5.index = pd.to_datetime(df5.index, utc=True)

    # Resample 5m → 10m
    df = df5.resample("10min", label="left", closed="left",
                      origin="start_day").agg(
        {"Open": "first", "High": "max", "Low": "min",
         "Close": "last", "Volume": "sum"})
    return df[df["Volume"] > 0].dropna()


# ── Indicators ────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    d["EMA_F"] = d["Close"].ewm(span=EMA_FAST_LEN, adjust=False).mean()
    d["EMA_M"] = d["Close"].ewm(span=EMA_MID_LEN,  adjust=False).mean()
    d["EMA_S"] = d["Close"].ewm(span=EMA_SLOW_LEN, adjust=False).mean()

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
    atr_s = d["ATR"].replace(0, np.nan)
    d["DI_PLUS"]  = 100 * pd.Series(pdm, index=d.index).ewm(alpha=1/ADX_LEN, adjust=False).mean() / atr_s
    d["DI_MINUS"] = 100 * pd.Series(ndm, index=d.index).ewm(alpha=1/ADX_LEN, adjust=False).mean() / atr_s
    dx  = (100 * (d["DI_PLUS"] - d["DI_MINUS"]).abs()
               / (d["DI_PLUS"] + d["DI_MINUS"]).replace(0, 1e-10))
    d["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()

    return d.dropna()


def _in_session(bar_ts) -> bool:
    ts = pd.Timestamp(bar_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return SESSION_START_ET <= ts.tz_convert(_ET).hour < SESSION_END_ET


# ── Signal evaluation ─────────────────────────────────────────────────────────
def check_signal(df: pd.DataFrame) -> dict | None:
    """Evaluate APM v2.0 short entry on the most recent completed 10m bar."""
    if len(df) < max(EMA_MID_LEN, MOMENTUM_BARS) + 5:
        return None

    bar  = df.iloc[-1]
    prev = df.iloc[-2]

    close  = float(bar["Close"])
    atr    = float(bar["ATR"])
    atr_bl = float(bar["ATR_BL"])

    if not _in_session(bar.name):
        log.debug("Outside session — skip")
        return None

    if float(bar["ADX"]) <= ADX_THRESH:
        log.debug("ADX %.2f ≤ %d — skip", float(bar["ADX"]), ADX_THRESH)
        return None
    if atr > atr_bl * PANIC_MULT:
        log.debug("PANIC mode — skip")
        return None
    if atr < close * ATR_FLOOR:
        log.debug("ATR floor — skip")
        return None

    if float(bar["Volume"]) < float(bar["VOL_MA"]) * VOL_MULT:
        log.debug("Volume filter — skip")
        return None
    body = abs(close - float(bar["Open"])) / atr
    if body < MIN_BODY:
        log.debug("Body filter — skip")
        return None

    ema_f_now  = float(bar["EMA_F"])
    ema_m_now  = float(bar["EMA_M"])
    ema_s_now  = float(bar["EMA_S"])
    ema_f_prev = float(prev["EMA_F"])
    rsi        = float(bar["RSI"])

    ema_bear = ema_f_now < ema_m_now and close < ema_s_now

    # Momentum: close < close[5]
    if MOMENTUM_BARS > 0 and len(df) > MOMENTUM_BARS + 2:
        if close >= float(df["Close"].iloc[-1 - MOMENTUM_BARS]):
            log.debug("Momentum filter — skip")
            return None

    if not (RSI_LO_S <= rsi <= RSI_HI_S):
        log.debug("RSI %.1f outside shorts band — skip", rsi)
        return None

    pb_tol_dn = ema_f_prev * (1.0 - PB_PCT / 100.0)
    short_pb  = (float(prev["High"]) >= pb_tol_dn
                 and close < ema_f_now
                 and close < float(bar["Open"]))

    if not (short_pb and ema_bear):
        log.info(
            "No signal  close=%.2f  ADX=%.1f  RSI=%.1f  body=%.3f  pb=%s  ema_bear=%s",
            close, float(bar["ADX"]), rsi, body, short_pb, ema_bear,
        )
        return None

    sl = close + atr * SL_MULT
    tp = close - atr * TP_MULT
    log.info(
        "SHORT SIGNAL: entry=%.2f  sl=%.2f  tp=%.2f  atr=%.2f  adx=%.1f  rsi=%.1f",
        close, sl, tp, atr, float(bar["ADX"]), rsi,
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


# ── Alpaca helpers ─────────────────────────────────────────────────────────────
def get_open_position(tc):
    try:
        return tc.get_open_position(SYMBOL.replace("/", ""))
    except Exception:
        return None


def cancel_order_safe(tc, order_id: str) -> None:
    try:
        tc.cancel_order_by_id(order_id)
        log.info("Cancelled order %s", order_id)
    except Exception as e:
        log.warning("cancel_order %s: %s", order_id, e)


def find_exit_fill(tc, pos: dict) -> tuple[float, str]:
    after_dt  = datetime.fromisoformat(pos["entry_time"])
    direction = pos["direction"]
    exit_side = "sell" if direction == "long" else "buy"
    try:
        orders = tc.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            symbols=[SYMBOL.replace("/", "")],
            after=after_dt,
            limit=10,
        ))
    except Exception as e:
        log.warning("get_orders failed: %s", e)
        return pos["sl"], "SL"

    for o in orders:
        if getattr(o.status, "value", None) == "filled" and o.filled_avg_price:
            oid = str(o.id)
            fp  = float(o.filled_avg_price)
            if oid == pos.get("tp_order_id"):
                return fp, "TP"
            if oid == pos.get("sl_order_id"):
                return fp, "SL"

    entry = pos["entry"]
    tp    = pos["tp"]
    for o in orders:
        if (getattr(o.status, "value", None) == "filled"
                and o.filled_avg_price
                and getattr(o.side, "value", None) == exit_side):
            fp = float(o.filled_avg_price)
            if direction == "short":
                if fp <= entry - (entry - tp) * 0.95:
                    return fp, "TP"
                elif fp > entry:
                    return fp, "SL"
                return fp, "Trail"
    return pos["sl"], "SL"


def submit_entry(tc, direction: str, qty: float) -> None:
    side = OrderSide.BUY if direction == "long" else OrderSide.SELL
    tc.submit_order(MarketOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        client_order_id=f"apm_btc_v2_entry_{int(datetime.now(timezone.utc).timestamp())}",
    ))


def submit_sl(tc, direction: str, qty: float, sl_price: float) -> str:
    side = OrderSide.SELL if direction == "long" else OrderSide.BUY
    o = tc.submit_order(StopOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        stop_price=round(sl_price, 2),
        client_order_id=f"apm_btc_v2_sl_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


def submit_tp(tc, direction: str, qty: float, tp_price: float) -> str:
    side = OrderSide.SELL if direction == "long" else OrderSide.BUY
    o = tc.submit_order(LimitOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        limit_price=round(tp_price, 2),
        client_order_id=f"apm_btc_v2_tp_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


def _record_closed_trade(state: dict, pos: dict, exit_price: float,
                         result: str, bars_held=None) -> None:
    entry     = pos["entry"]
    notional  = pos["notional"]
    direction = pos["direction"]
    pnl_pct   = ((exit_price - entry) / entry if direction == "long"
                 else (entry - exit_price) / entry)
    dollar_pnl = pnl_pct * notional - notional * COMMISSION_PCT * 2
    state["equity"] += dollar_pnl

    if result == "SL":
        state["consec_losses"] = state.get("consec_losses", 0) + 1
        if state["consec_losses"] >= CONSEC_LOSS_LIMIT:
            log.info("Cooldown triggered (%d consecutive SL)", CONSEC_LOSS_LIMIT)
            state["cooldown_bars"] = CONSEC_LOSS_COOLDOWN
            state["consec_losses"] = 0
    else:
        state["consec_losses"] = 0

    if bars_held is None:
        bars_held = pos.get("bars_in_trade", "?")

    append_trade({
        "entry_time":  pos["entry_time"],
        "exit_time":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00"),
        "direction":   direction,
        "entry":       round(entry, 2),
        "exit":        round(exit_price, 2),
        "exit_reason": result,
        "bars_held":   bars_held,
        "pnl_pct":     round(pnl_pct * 100, 3),
        "dollar_pnl":  round(dollar_pnl, 2),
        "equity":      round(state["equity"], 2),
    })
    log.info(
        "Closed: %s %s  exit=%.2f  bars=%s  pnl=%+.2f  equity=%.2f",
        result, direction, exit_price, bars_held, dollar_pnl, state["equity"],
    )
    state["position"] = None


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("=== APM v2.0 Paper Trader — %s 10m (shorts only) ===", SYMBOL)

    if not API_KEY or not API_SECRET:
        log.error("Missing credentials — set ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET.")
        sys.exit(1)

    data_client    = CryptoHistoricalDataClient(API_KEY, API_SECRET)
    trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

    log.info("Fetching %s 5m bars → resampling to 10m (60d)…", SYMBOL)
    df = fetch_bars(data_client)
    if df.empty or len(df) < MIN_BARS:
        log.warning("Insufficient bars (%d < %d) — skipping.", len(df), MIN_BARS)
        return

    df = compute_indicators(df)
    if df.empty:
        return

    df = df.iloc[:-1]
    if df.empty:
        return

    last_bar_ts = str(df.index[-1])
    log.info("Bars: %d  last_closed=%s  close=%.2f",
             len(df), last_bar_ts, df["Close"].iloc[-1])

    state   = load_state()
    pos     = state.get("position")
    new_bar = (last_bar_ts != state.get("last_bar_ts"))

    if pos is not None:
        alpaca_pos = get_open_position(trading_client)

        if alpaca_pos is None:
            log.info("Position closed externally — recording trade.")
            exit_price, result = find_exit_fill(trading_client, pos)
            for oid in (pos.get("sl_order_id"), pos.get("tp_order_id")):
                if oid and oid != "unknown":
                    cancel_order_safe(trading_client, oid)
            _record_closed_trade(state, pos, exit_price, result)
            state["last_bar_ts"] = last_bar_ts
            save_state(state)
            return

        if new_bar:
            bars_held = pos.get("bars_in_trade", 0) + 1
            pos["bars_in_trade"] = bars_held
            log.info("Bars in trade: %d / %d", bars_held, MAX_BARS)

            if bars_held >= MAX_BARS:
                log.info("MaxBars reached — closing at market.")
                for oid in (pos.get("sl_order_id"), pos.get("tp_order_id")):
                    if oid and oid != "unknown":
                        cancel_order_safe(trading_client, oid)
                try:
                    qty = float(alpaca_pos.qty_available)
                    close_side = "long" if pos["direction"] == "short" else "short"
                    submit_entry(trading_client, close_side, qty)
                    time.sleep(3)
                except Exception as e:
                    log.error("Market close failed: %s", e)
                exit_price = float(df.iloc[-1]["Close"])
                _record_closed_trade(state, pos, exit_price, "MB", bars_held)
                state["last_bar_ts"] = last_bar_ts
                save_state(state)
                return

            # Trailing stop update
            direction  = pos["direction"]
            trail_dist = pos["entry_atr"] * TRAIL_DIST
            bar_high   = float(df.iloc[-1]["High"])
            bar_low    = float(df.iloc[-1]["Low"])

            if direction == "short":
                new_best = min(pos["best"], bar_low)
                pos["best"] = new_best
                if new_best <= pos["trail_activate_px"]:
                    new_sl = new_best + trail_dist
                    if new_sl < pos["sl"]:
                        log.info("Trail(S): SL %.2f → %.2f", pos["sl"], new_sl)
                        prior_sl = pos["sl"]
                        if pos.get("sl_order_id") not in (None, "unknown"):
                            cancel_order_safe(trading_client, pos["sl_order_id"])
                        try:
                            qty    = float(alpaca_pos.qty_available)
                            new_id = submit_sl(trading_client, "short", qty, new_sl)
                            pos["sl"] = new_sl
                            pos["sl_order_id"] = new_id
                        except Exception as e:
                            pos["sl"] = prior_sl
                            pos["sl_order_id"] = "unknown"
                            log.error("SL update failed; stop order is now untracked: %s", e)

        state["position"]    = pos
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        log.info(
            "Position open (%s): bars=%d  SL=%.2f  TP=%.2f",
            pos["direction"], pos.get("bars_in_trade", 0), pos["sl"], pos["tp"],
        )
        return

    if get_open_position(trading_client) is not None:
        log.warning("Untracked open position — skipping entry.")
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    if not new_bar:
        log.info("Same bar as last run — nothing to do.")
        return

    if state.get("cooldown_bars", 0) > 0:
        state["cooldown_bars"] -= 1
        log.info("Cooldown: %d bar(s) remaining — skipping.", state["cooldown_bars"])
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    signal = check_signal(df)
    if signal is None:
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        return

    eq        = state["equity"]
    stop_dist = abs(signal["entry"] - signal["sl"])
    qty       = round(eq * RISK_PCT / stop_dist, 6)
    qty       = max(0.0001, qty)
    notional  = qty * signal["entry"]
    if notional > eq * LEV_CAP:
        qty      = round(eq * LEV_CAP / signal["entry"], 6)
        qty      = max(0.0001, qty)
        notional = qty * signal["entry"]

    direction = signal["direction"]
    log.info(
        "Entering %s: qty=%.6f  entry~%.2f  notional~$%.2f",
        direction, qty, signal["entry"], notional,
    )

    entry_ts    = datetime.now(timezone.utc).isoformat()
    sl_order_id = tp_order_id = "unknown"

    try:
        submit_entry(trading_client, direction, qty)
        log.info("Market %s submitted.", direction)
    except Exception as e:
        log.error("Entry failed: %s", e)
        return

    time.sleep(2)

    try:
        sl_order_id = submit_sl(trading_client, direction, qty, signal["sl"])
    except Exception as e:
        log.error("SL failed: %s", e)

    try:
        tp_order_id = submit_tp(trading_client, direction, qty, signal["tp"])
    except Exception as e:
        log.error("TP failed: %s", e)

    state["position"] = {
        "entry_time":        entry_ts,
        "direction":         direction,
        "entry":             signal["entry"],
        "sl":                signal["sl"],
        "tp":                signal["tp"],
        "best":              signal["entry"],
        "notional":          notional,
        "trail_activate_px": signal["trail_activate_px"],
        "entry_atr":         signal["entry_atr"],
        "bars_in_trade":     0,
        "sl_order_id":       sl_order_id,
        "tp_order_id":       tp_order_id,
    }
    state["last_bar_ts"] = last_bar_ts
    save_state(state)
    log.info("Position state saved.")


if __name__ == "__main__":
    main()
