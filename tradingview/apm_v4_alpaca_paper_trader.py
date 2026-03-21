# Scheduling: Run every 30 minutes at bar close via cron or GitHub Actions.
# Example cron: */30 * * * * /home/rcaldwell67/repo/pinescripts/.venv/bin/python /home/rcaldwell67/repo/pinescripts/apm_v4_alpaca_paper_trader.py
#
# To maximize net return, additional logic added:
# - Trailing stop: activates once price moves ATR×4 in favor, trail stays ATR×1.5 from best price
# - Session gating: entries only 09:00–14:00 ET
# - Max bars exit: position closed after 24 bars (12 hours)
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

# Load environment variables
load_dotenv()
API_KEY = os.getenv('ALPACA_PAPER_API_KEY')
API_SECRET = os.getenv('ALPACA_PAPER_API_SECRET')

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger("apm_v4_paper")

# Strategy parameters (adapted from v3, 30m)
SYMBOL = 'BTC/USD'
INITIAL_CAPITAL = 10000.0
COMMISSION_PCT = 0.0006
RISK_PCT = 0.03
LEV_CAP = 5.0

EMA_FAST_LEN = 21
EMA_MID_LEN  = 50
EMA_SLOW_LEN = 200
ADX_LEN      = 14
RSI_LEN      = 14
ATR_LEN      = 14
ATR_BL_LEN   = 50
VOL_LEN      = 20

ADX_THRESH = 28
PB_PCT     = 0.15
VOL_MULT   = 1.2
MIN_BODY   = 0.20
ATR_FLOOR  = 0.0015
PANIC_MULT = 1.3

RSI_LO_L = 42; RSI_HI_L = 68
RSI_LO_S = 32; RSI_HI_S = 58

SL_MULT    = 2.0
TP_MULT    = 2.0
TRAIL_ACT  = 1.5
TRAIL_DIST = 1.5

TRADE_LONGS  = False
TRADE_SHORTS = True

MIN_BARS = EMA_SLOW_LEN + ATR_BL_LEN + 10
TIMEFRAME = TimeFrame(30, TimeFrameUnit.Minute)
STATE_FILE = Path("docs/data/btcusd/v4_paper_state.json")
TRADES_FILE = Path("docs/data/btcusd/v4_trades_paper.csv")
TRADES_COLS = [
    "entry_time", "exit_time", "direction", "entry", "exit",
    "exit_reason", "bars_held", "pnl_pct", "dollar_pnl", "equity",
]

def load_state():
    if STATE_FILE.exists():
        try:
            s = json.loads(STATE_FILE.read_text())
            s.setdefault("position",    None)
            s.setdefault("equity",      INITIAL_CAPITAL)
            s.setdefault("last_bar_ts", None)
            return s
        except Exception:
            pass
    return {"position": None, "equity": INITIAL_CAPITAL, "last_bar_ts": None}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))

def append_trade(trade):
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_file = not TRADES_FILE.exists()
    with open(TRADES_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRADES_COLS)
        if new_file:
            w.writeheader()
        w.writerow({k: trade.get(k, "") for k in TRADES_COLS})
    log.info("Trade appended → %s", TRADES_FILE.name)

def fetch_bars():
    client = CryptoHistoricalDataClient()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=90)
    req = CryptoBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TIMEFRAME,
        start=start,
        end=end,
    )
    try:
        bars = client.get_crypto_bars(req)
        df = bars.df.reset_index()
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
    df.index = pd.to_datetime(df.index, utc=True)
    return df

def compute_indicators(df):
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

def check_signal(df):
    if len(df) < 5:
        return None
    bar  = df.iloc[-1]
    prev = df.iloc[-2]
    close  = float(bar["Close"])
    atr    = float(bar["ATR"])
    atr_bl = float(bar["ATR_BL"])
    if float(bar["ADX"]) <= ADX_THRESH:
        log.debug(f"ADX {bar['ADX']:.2f} <= {ADX_THRESH} — skip")
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
    if not (RSI_LO_S <= rsi <= RSI_HI_S):
        log.debug(f"RSI {rsi:.1f} outside shorts band — skip")
        return None
    pb_tol_dn = ema_f_prev * (1.0 - PB_PCT / 100.0)
    short_pb  = (float(prev["High"]) >= pb_tol_dn
                 and close < ema_f_now
                 and close < float(bar["Open"]))
    if not (short_pb and ema_bear):
        log.info(
            f"No signal  close={close:.2f}  ADX={bar['ADX']:.1f}  RSI={rsi:.1f}  pb={short_pb}  ema_bear={ema_bear}")
        return None
    sl = close + atr * SL_MULT
    tp = close - atr * TP_MULT
    log.info(
        f"SHORT SIGNAL: entry={close:.2f}  sl={sl:.2f}  tp={tp:.2f}  atr={atr:.2f}  adx={bar['ADX']:.1f}  rsi={rsi:.1f}")
    return {
        "direction":         "short",
        "entry":             close,
        "sl":                sl,
        "tp":                tp,
        "trail_activate_px": close - atr * TRAIL_ACT,
        "trail_dist_atr":    atr * TRAIL_DIST,
        "entry_atr":         atr,
    }

def main():
    trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
    state = load_state()
    df = fetch_bars()
    if df.empty:
        log.error("No data fetched.")
        return
    df = compute_indicators(df)
    last_bar = df.iloc[-1]
    now = datetime.now(timezone.utc)
    et = now.astimezone(timezone(timedelta(hours=-4)))
    if not (9 <= et.hour < 14):
        log.info("Session gating: not entry window.")
        return
    signal = check_signal(df)
    equity = state.get("equity", INITIAL_CAPITAL)
    MAX_BARS = 24
    if state["position"] is None:
        if signal:
            direction = signal["direction"]
            qty = (equity * RISK_PCT) / last_bar["Close"]
            side = OrderSide.SELL
            order = MarketOrderRequest(
                symbol=SYMBOL.replace("/", ""),
                qty=qty,
                side=side,
                time_in_force=TimeInForce.GTC
            )
            trading_client.submit_order(order)
            log.info(f"{direction.title()} order placed: {qty:.4f} {SYMBOL} at {last_bar['Close']}")
            state["position"] = {
                "direction": direction,
                "entry_time": str(last_bar.name),
                "entry": last_bar["Close"],
                "qty": qty,
                "equity": equity,
                "bars_held": 0,
                "best": last_bar["Close"],
                "trail_active": False,
                "trail_px": None,
            }
            save_state(state)
    else:
        direction = state["position"]["direction"]
        entry = state["position"]["entry"]
        qty = state["position"]["qty"]
        bars_held = state["position"].get("bars_held", 0) + 1
        best = state["position"].get("best", entry)
        best = min(best, last_bar["Close"])
        trail_active = state["position"].get("trail_active", False)
        trail_px = state["position"].get("trail_px", None)
        atr = last_bar["High"] - last_bar["Low"]
        activate_px = entry - TRAIL_ACT * atr
        if not trail_active:
            if best <= activate_px:
                trail_active = True
                trail_px = best + TRAIL_DIST * atr
                log.info(f"Trailing stop activated at {trail_px:.2f}")
        exit = False
        exit_reason = ""
        if trail_active:
            if last_bar["High"] >= trail_px:
                exit = True
                exit_reason = "TRAIL"
        if bars_held >= MAX_BARS:
            exit = True
            exit_reason = "MAX_BARS"
        pnl = (entry - last_bar["Close"]) * qty
        equity += pnl
        if exit:
            trade = {
                "entry_time": state["position"]["entry_time"],
                "exit_time": str(last_bar.name),
                "direction": direction,
                "entry": entry,
                "exit": last_bar["Close"],
                "exit_reason": exit_reason,
                "bars_held": bars_held,
                "pnl_pct": round(pnl / (entry * qty) * 100, 2),
                "dollar_pnl": round(pnl, 2),
                "equity": round(equity, 2),
            }
            append_trade(trade)
            log.info(f"Position closed: {direction} {qty:.4f} {SYMBOL} at {last_bar['Close']} P&L: {pnl:.2f} Reason: {exit_reason}")
            state["position"] = None
            state["equity"] = equity
        else:
            state["position"] = {
                "direction": direction,
                "entry_time": state["position"]["entry_time"],
                "entry": entry,
                "qty": qty,
                "equity": equity,
                "bars_held": bars_held,
                "best": best,
                "trail_active": trail_active,
                "trail_px": trail_px,
            }
        save_state(state)

if __name__ == "__main__":
    main()

import os
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

# Load environment variables
load_dotenv()
API_KEY = os.getenv('ALPACA_PAPER_API_KEY')
API_SECRET = os.getenv('ALPACA_PAPER_API_SECRET')

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger("apm_v4_paper")

# Strategy parameters
TP_MULT = 4.0
SL_MULT = 2.0
RISK_PCT = 0.03
VOL_MULT = 1.0
ADX_THRESH = 15
INITIAL_CAPITAL = 10000.0
SYMBOL = 'BTC/USD'
TIMEFRAME = TimeFrame(30, TimeFrameUnit.Minute)
STATE_FILE = Path("docs/data/btcusd/v4_paper_state.json")
TRADES_FILE = Path("docs/data/btcusd/v4_trades_paper.csv")
TRADES_COLS = ["entry_time", "exit_time", "direction", "entry", "exit", "result", "pnl_pct", "dollar_pnl", "equity"]

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"position": None}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

def append_trade(trade):
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_file = not TRADES_FILE.exists()
    with open(TRADES_FILE, "a", newline="") as f:
        w = pd.DataFrame([trade])
        if new_file:
            w.to_csv(f, header=True, index=False)
        else:
            w.to_csv(f, header=False, index=False)
    log.info("Trade appended → %s", TRADES_FILE.name)

def fetch_bars():
    client = CryptoHistoricalDataClient()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    req = CryptoBarsRequest(symbol_or_symbols=[SYMBOL], timeframe=TIMEFRAME, start=start, end=end)
    try:
        bars = client.get_crypto_bars(req)
        df = bars.df.reset_index()
    except Exception as e:
        log.error("fetch_bars failed: %s", e)
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()
    df = (df[df["symbol"] == SYMBOL]
            .copy()
            .sort_values("timestamp")
            .set_index("timestamp")
            [["open", "high", "low", "close", "volume"]]
            .rename(columns=str.title))
    return df[df["Volume"] > 0].dropna()

def compute_indicators(df):
    d = df.copy()
    d["EMA_FAST"] = d["Close"].ewm(span=21, adjust=False).mean()
    d["EMA_MID"]  = d["Close"].ewm(span=50,  adjust=False).mean()
    d["EMA_SLOW"] = d["Close"].ewm(span=200, adjust=False).mean()
    d["VOL_MA"]   = d["Volume"].rolling(20).mean()
    # Placeholder ADX
    d["ADX"] = (d["High"] - d["Low"]).rolling(14).mean()
    return d

def main():
    trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
    state = load_state()
    df = fetch_bars()
    if df.empty:
        log.error("No data fetched.")
        return
    df = compute_indicators(df)
    last_bar = df.iloc[-1]
    now = datetime.now(timezone.utc)
    # Session gating: only enter trades 09:00–14:00 ET
    et = now.astimezone(timezone(timedelta(hours=-4)))
    if not (9 <= et.hour < 14):
        log.info("Session gating: not entry window.")
        return
    long_signal = (
        (last_bar["EMA_FAST"] > last_bar["EMA_MID"]) and
        (last_bar["EMA_MID"] > last_bar["EMA_SLOW"]) and
        (last_bar["Volume"] >= last_bar["VOL_MA"] * VOL_MULT) and
        (last_bar["ADX"] > ADX_THRESH)
    )
    short_signal = (
        (last_bar["EMA_FAST"] < last_bar["EMA_MID"]) and
        (last_bar["EMA_MID"] < last_bar["EMA_SLOW"]) and
        (last_bar["Volume"] >= last_bar["VOL_MA"] * VOL_MULT) and
        (last_bar["ADX"] > ADX_THRESH)
    )
    equity = state.get("equity", INITIAL_CAPITAL)
    # Trailing stop and max bars logic
    TRAIL_ACT = 4.0
    TRAIL_DIST = 1.5
    MAX_BARS = 24
    if state["position"] is None:
        if long_signal or short_signal:
            direction = "long" if long_signal else "short"
            qty = (equity * RISK_PCT) / last_bar["Close"]
            side = OrderSide.BUY if direction == "long" else OrderSide.SELL
            order = MarketOrderRequest(
                symbol=SYMBOL.replace("/", ""),
                qty=qty,
                side=side,
                time_in_force=TimeInForce.GTC
            )
            trading_client.submit_order(order)
            log.info(f"{direction.title()} order placed: {qty:.4f} {SYMBOL} at {last_bar['Close']}")
            state["position"] = {
                "direction": direction,
                "entry_time": str(last_bar.name),
                "entry": last_bar["Close"],
                "qty": qty,
                "equity": equity,
                "bars_held": 0,
                "best": last_bar["Close"],
                "trail_active": False,
                "trail_px": None,
            }
            save_state(state)
    else:
        direction = state["position"]["direction"]
        entry = state["position"]["entry"]
        qty = state["position"]["qty"]
        bars_held = state["position"].get("bars_held", 0) + 1
        best = state["position"].get("best", entry)
        # Update best price
        if direction == "long":
            best = max(best, last_bar["Close"])
        else:
            best = min(best, last_bar["Close"])
        # Trailing stop logic
        trail_active = state["position"].get("trail_active", False)
        trail_px = state["position"].get("trail_px", None)
        atr = last_bar["High"] - last_bar["Low"]
        activate_px = entry + TRAIL_ACT * atr if direction == "long" else entry - TRAIL_ACT * atr
        if not trail_active:
            if (direction == "long" and best >= activate_px) or (direction == "short" and best <= activate_px):
                trail_active = True
                trail_px = best - TRAIL_DIST * atr if direction == "long" else best + TRAIL_DIST * atr
                log.info(f"Trailing stop activated at {trail_px:.2f}")
        # Exit conditions
        exit = False
        exit_reason = ""
        if trail_active:
            if (direction == "long" and last_bar["Low"] <= trail_px) or (direction == "short" and last_bar["High"] >= trail_px):
                exit = True
                exit_reason = "TRAIL"
        if bars_held >= MAX_BARS:
            exit = True
            exit_reason = "MAX_BARS"
        pnl = (last_bar["Close"] - entry) * qty if direction == "long" else (entry - last_bar["Close"]) * qty
        equity += pnl
        if exit:
            trade = {
                "entry_time": state["position"]["entry_time"],
                "exit_time": str(last_bar.name),
                "direction": direction,
                "entry": entry,
                "exit": last_bar["Close"],
                "result": exit_reason,
                "pnl_pct": round(pnl / (entry * qty) * 100, 2),
                "dollar_pnl": round(pnl, 2),
                "equity": round(equity, 2),
            }
            append_trade(trade)
            log.info(f"Position closed: {direction} {qty:.4f} {SYMBOL} at {last_bar['Close']} P&L: {pnl:.2f} Reason: {exit_reason}")
            state["position"] = None
            state["equity"] = equity
        else:
            state["position"] = {
                "direction": direction,
                "entry_time": state["position"]["entry_time"],
                "entry": entry,
                "qty": qty,
                "equity": equity,
                "bars_held": bars_held,
                "best": best,
                "trail_active": trail_active,
                "trail_px": trail_px,
            }
        save_state(state)

if __name__ == "__main__":
    main()
