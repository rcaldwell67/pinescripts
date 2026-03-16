"""
paper_trader_v6.py — APM v6.3 paper trading bot, CLM 1D (longs only).

Run once per day at/after NYSE close via GitHub Actions.  Each run checks
whether a new completed daily bar is available; if so it evaluates the
APM v6.3 entry conditions and manages any open position (SL, TP, MaxBars
time-exit).

State persisted in docs/data/clm/v6_paper_state.json between runs:
    position      – open trade dict or null
    equity        – tracked equity (updated on each closed trade)
    last_bar_ts   – last 1D bar timestamp processed (dedup)

Completed trades appended to docs/data/clm/v6_trades_paper.csv.

Run manually:
    cd /workspaces/pinescripts/docs
    python paper_trader_v6.py

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
from alpaca.data.timeframe import TimeFrame
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
log = logging.getLogger("apm_v6_paper")

# ── Paths ─────────────────────────────────────────────────────────────────────
_DOCS       = Path(__file__).parent
STATE_FILE  = _DOCS / "data" / "clm" / "v6_paper_state.json"
TRADES_FILE = _DOCS / "data" / "clm" / "v6_trades_paper.csv"
TRADES_COLS = [
    "entry_time", "exit_time", "direction", "entry", "exit",
    "result", "bars_held", "pnl_pct", "dollar_pnl", "equity",
]

# ── Credentials ───────────────────────────────────────────────────────────────
API_KEY    = (os.environ.get("ALPACA_PAPER_API_KEY")
              or os.environ.get("ALPACA_API_KEY", ""))
API_SECRET = (os.environ.get("ALPACA_PAPER_API_SECRET")
              or os.environ.get("ALPACA_API_SECRET", ""))

# ── APM v6.3 parameters (CLM 1D — matches Adaptive Pullback Momentum v6.0.pine) ──
SYMBOL          = "CLM"
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006   # 0.06% per side

# Indicator lengths
EMA_FAST_LEN    = 21
EMA_MID_LEN     = 34
EMA_SLOW_LEN    = 200
ADX_LEN         = 14
RSI_LEN         = 14
ATR_LEN         = 14
ATR_BL_LEN      = 60    # ATR baseline rolling mean period
VOL_LEN         = 20

# Entry filters
ADX_THRESH      = 20      # ADX must exceed this
PB_PCT          = 0.30    # pullback tolerance: prev low within 0.30% of EMA-fast
VOL_MULT        = 1.0     # volume ≥ 1.0× vol SMA
MIN_BODY        = 0.20    # candle body ≥ 0.20×ATR
PANIC_MULT      = 2.0     # ATR > ATR_BL×2.0 → suppress entries
ATR_FLOOR       = 0.0     # no floor (not used on 1D)
EMA_MID_SLOPE_LB = 8      # EMA_MID must be rising vs N bars ago (0=off)

# RSI bounds (longs only)
RSI_LO_L = 42
RSI_HI_L = 75

# Exit params
SL_MULT    = 1.5    # SL = entry − ATR × 1.5
TP_MULT    = 3.5    # TP = entry + ATR × 3.5
TRAIL_ACT  = 99.0   # trail disabled (99× ATR never activates on daily bars)
MAX_BARS   = 25     # time-stop: exit at bar close after 25 bars

# Risk sizing
RISK_PCT   = 0.01   # 1.0% of equity risked per trade
LEV_CAP    = 5.0    # max leverage cap

# Minimum bars needed for indicator warmup
MIN_BARS = EMA_SLOW_LEN + ATR_BL_LEN + 10   # ~270 bars


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
    """Fetch ~400 days of CLM 1D bars for indicator warmup."""
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=400)
    req   = StockBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TimeFrame.Day,
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
    return df


# ── Indicators ────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    d["EMA_F"] = d["Close"].ewm(span=EMA_FAST_LEN, adjust=False).mean()
    d["EMA_M"] = d["Close"].ewm(span=EMA_MID_LEN,  adjust=False).mean()
    d["EMA_S"] = d["Close"].ewm(span=EMA_SLOW_LEN, adjust=False).mean()

    delta = d["Close"].diff()
    g     = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    lv    = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
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
    Evaluate APM v6.3 long entry conditions on the most recently completed 1D bar.
    Returns entry dict or None.
    """
    if len(df) < EMA_MID_SLOPE_LB + 5:
        return None

    bar  = df.iloc[-1]   # most recent completed bar
    prev = df.iloc[-2]   # previous bar (the pullback bar)

    close  = float(bar["Close"])
    opn    = float(bar["Open"])
    atr    = float(bar["ATR"])
    atr_bl = float(bar["ATR_BL"])
    rsi    = float(bar["RSI"])
    adx    = float(bar["ADX"])

    # ── Regime guards ──────────────────────────────────────────────────────
    if adx <= ADX_THRESH:
        log.debug("ADX %.2f ≤ %d — skip", adx, ADX_THRESH)
        return None
    if atr > atr_bl * PANIC_MULT:
        log.debug("PANIC mode (ATR %.4f > %.4f × %.1f) — skip", atr, atr_bl, PANIC_MULT)
        return None

    # ── Volume & body filters ──────────────────────────────────────────────
    if float(bar["Volume"]) < float(bar["VOL_MA"]) * VOL_MULT:
        log.debug("Volume %.2fx < %.1fx — skip",
                  float(bar["Volume"]) / float(bar["VOL_MA"]), VOL_MULT)
        return None

    body = abs(close - opn) / atr
    if body < MIN_BODY:
        log.debug("Body %.3f < %.3f — skip", body, MIN_BODY)
        return None

    ema_f_now  = float(bar["EMA_F"])
    ema_m_now  = float(bar["EMA_M"])
    ema_s_now  = float(bar["EMA_S"])
    ema_f_prev = float(prev["EMA_F"])

    # ── EMA mid slope filter ───────────────────────────────────────────────
    if EMA_MID_SLOPE_LB > 0:
        ema_m_past = float(df["EMA_M"].iloc[-1 - EMA_MID_SLOPE_LB])
        if ema_m_now <= ema_m_past:
            log.debug("EMA_M slope flat/falling (%.4f ≤ %.4f [%d bars ago]) — skip",
                      ema_m_now, ema_m_past, EMA_MID_SLOPE_LB)
            return None

    # ── RSI bounds ─────────────────────────────────────────────────────────
    if not (RSI_LO_L <= rsi <= RSI_HI_L):
        log.debug("RSI %.1f outside [%d, %d] — skip", rsi, RSI_LO_L, RSI_HI_L)
        return None

    # ── Pullback condition (prev bar tagged EMA-fast) ─────────────────────
    pb_tol_up = ema_f_prev * (1.0 + PB_PCT / 100.0)
    long_pb   = (float(prev["Low"]) <= pb_tol_up
                 and close > ema_f_now
                 and close > opn)   # bullish close on entry bar

    # ── EMA stack (bull) ───────────────────────────────────────────────────
    ema_bull  = ema_f_now > ema_m_now and close > ema_s_now

    if long_pb and ema_bull:
        sl = close - atr * SL_MULT
        tp = close + atr * TP_MULT
        log.info(
            "LONG SIGNAL: entry=%.4f  sl=%.4f  tp=%.4f  "
            "atr=%.4f  adx=%.1f  rsi=%.1f  body=%.3f  vol=%.2fx  "
            "ema_f=%.4f  ema_m=%.4f  ema_s=%.4f",
            close, sl, tp, atr, adx, rsi, body,
            float(bar["Volume"]) / float(bar["VOL_MA"]),
            ema_f_now, ema_m_now, ema_s_now,
        )
        return {
            "direction":  "long",
            "entry":      close,
            "sl":         sl,
            "tp":         tp,
            "entry_atr":  atr,
        }

    log.info(
        "No signal (close=%.4f  ADX=%.1f  RSI=%.1f  body=%.3f  "
        "pb=%s  ema_bull=%s  EMA_F=%.4f  EMA_M=%.4f  EMA_S=%.4f)",
        close, adx, rsi, body,
        long_pb, ema_bull, ema_f_now, ema_m_now, ema_s_now,
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
    """Scan recent closed orders to classify exit as SL or TP."""
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

    entry = pos["entry"]
    tp    = pos["tp"]

    for o in orders:
        if getattr(o.status, "value", None) == "filled" and o.filled_avg_price:
            oid = str(o.id)
            fp  = float(o.filled_avg_price)
            if oid == pos.get("tp_order_id"):
                return fp, "TP"
            if oid == pos.get("sl_order_id"):
                return fp, "SL"

    # Price-based fallback
    for o in orders:
        if (getattr(o.status, "value", None) == "filled"
                and o.filled_avg_price
                and getattr(o.side, "value", None) == "sell"):
            fp = float(o.filled_avg_price)
            if fp >= entry + (tp - entry) * 0.90:
                return fp, "TP"
            elif fp < entry:
                return fp, "SL"
            else:
                return fp, "SL"

    return pos["sl"], "SL"


def submit_market_close(tc, qty: int) -> None:
    tc.submit_order(MarketOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        client_order_id=f"apm6_mb_{int(datetime.now(timezone.utc).timestamp())}",
    ))


def submit_sl(tc, qty: int, sl_price: float) -> str:
    o = tc.submit_order(StopOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC,
        stop_price=round(sl_price, 2),
        client_order_id=f"apm6_sl_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


def submit_tp(tc, qty: int, tp_price: float) -> str:
    o = tc.submit_order(LimitOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC,
        limit_price=round(tp_price, 2),
        client_order_id=f"apm6_tp_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("=== APM v6.3 Paper Trader — %s 1D (longs only) ===", SYMBOL)

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
        if clock.is_open:
            log.info("Market still open — waiting for daily bar close.")
            return
    except Exception as e:
        log.warning("Could not check market clock (%s) — proceeding anyway.", e)

    # ── Fetch + compute indicators ─────────────────────────────────────────────
    log.info("Fetching %s 1D bars (400d)…", SYMBOL)
    df = fetch_bars(data_client)
    if df.empty or len(df) < MIN_BARS:
        log.warning("Insufficient bars (%d < %d) — skipping.", len(df), MIN_BARS)
        return

    df = compute_indicators(df)
    if df.empty:
        log.warning("Empty frame after indicators — skipping.")
        return

    # Drop any incomplete bar (current day if market just closed may still be incomplete)
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

    if not new_bar:
        log.info("Same bar as last run (ts=%s) — nothing to do.", last_bar_ts)
        return

    # ── Manage open position ───────────────────────────────────────────────────
    if pos is not None:
        alpaca_pos = get_open_position(trading_client)

        # ── External close (SL or TP filled by broker) ─────────────────────
        if alpaca_pos is None:
            log.info("Position closed externally — recording trade.")
            exit_price, result = find_exit_fill(trading_client, pos)
            _record_closed_trade(state, pos, exit_price, result)
            save_state(state)
            return

        # ── MaxBars time-stop ───────────────────────────────────────────────
        bars_held = pos.get("bars_in_trade", 0) + 1
        pos["bars_in_trade"] = bars_held
        log.info("Bars in trade: %d / %d", bars_held, MAX_BARS)

        if bars_held >= MAX_BARS:
            log.info("MaxBars (%d) reached — closing position at market.", MAX_BARS)
            # Cancel SL and TP before submitting market close
            for oid in (pos.get("sl_order_id"), pos.get("tp_order_id")):
                if oid and oid != "unknown":
                    cancel_order_safe(trading_client, oid)
            try:
                qty = abs(int(float(alpaca_pos.qty)))
                submit_market_close(trading_client, qty)
                time.sleep(3)
            except Exception as e:
                log.error("Market close failed: %s", e)

            # Use last known bar close as exit approximation
            exit_price = float(df.iloc[-1]["Close"])
            _record_closed_trade(state, pos, exit_price, "MB", bars_held)
            save_state(state)
            return

        # Position still open and MaxBars not reached — just save updated bar count
        state["position"]    = pos
        state["last_bar_ts"] = last_bar_ts
        save_state(state)
        log.info(
            "Position open (long): bars_held=%d  SL=%.4f  TP=%.4f",
            bars_held, pos["sl"], pos["tp"],
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

    # ── Entry signal ───────────────────────────────────────────────────────────
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
    if notional > eq * LEV_CAP:
        qty      = max(1, int(eq * LEV_CAP / signal["entry"]))
        notional = qty * signal["entry"]

    log.info(
        "Entering LONG: qty=%d  entry~%.4f  notional~$%.2f  stop_dist=%.4f  risk~$%.2f",
        qty, signal["entry"], notional, stop_dist, qty * stop_dist,
    )

    entry_ts    = datetime.now(timezone.utc).isoformat()
    sl_order_id = tp_order_id = "unknown"

    try:
        trading_client.submit_order(MarketOrderRequest(
            symbol=SYMBOL,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            client_order_id=f"apm6_entry_{int(datetime.now(timezone.utc).timestamp())}",
        ))
        log.info("Market BUY order submitted.")
    except Exception as e:
        log.error("Entry order failed: %s", e)
        return

    time.sleep(2)

    try:
        sl_order_id = submit_sl(trading_client, qty, signal["sl"])
        log.info("SL order: id=%s  price=%.4f", sl_order_id, signal["sl"])
    except Exception as e:
        log.error("SL order failed: %s", e)

    try:
        tp_order_id = submit_tp(trading_client, qty, signal["tp"])
        log.info("TP order: id=%s  price=%.4f", tp_order_id, signal["tp"])
    except Exception as e:
        log.error("TP order failed: %s", e)

    state["position"] = {
        "entry_time":   entry_ts,
        "direction":    "long",
        "entry":        signal["entry"],
        "sl":           signal["sl"],
        "tp":           signal["tp"],
        "notional":     notional,
        "entry_atr":    signal["entry_atr"],
        "bars_in_trade": 0,
        "sl_order_id":  sl_order_id,
        "tp_order_id":  tp_order_id,
    }
    state["last_bar_ts"] = last_bar_ts
    save_state(state)
    log.info("Position state saved.")


def _record_closed_trade(state: dict, pos: dict, exit_price: float,
                         result: str, bars_held: int | None = None) -> None:
    """Compute PnL, update equity, append to CSV, reset position in state."""
    entry      = pos["entry"]
    notional   = pos["notional"]
    pnl_pct    = (exit_price - entry) / entry
    dollar_pnl = pnl_pct * notional - notional * COMMISSION_PCT * 2
    state["equity"] += dollar_pnl

    if bars_held is None:
        bars_held = pos.get("bars_in_trade", "?")

    append_trade({
        "entry_time": pos["entry_time"],
        "exit_time":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00"),
        "direction":  "long",
        "entry":      round(entry, 4),
        "exit":       round(exit_price, 4),
        "result":     result,
        "bars_held":  bars_held,
        "pnl_pct":    round(pnl_pct * 100, 3),
        "dollar_pnl": round(dollar_pnl, 2),
        "equity":     round(state["equity"], 2),
    })

    log.info(
        "Closed: %s  exit=%.4f  bars=%s  pnl=%+.2f  equity=%.2f",
        result, exit_price, bars_held, dollar_pnl, state["equity"],
    )
    state["position"]    = None
    state["last_bar_ts"] = str(datetime.now(timezone.utc).date())


if __name__ == "__main__":
    main()
