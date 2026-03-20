# Scheduling: Run every 30 minutes at bar close via cron or GitHub Actions.
# Example cron: */30 * * * * /home/rcaldwell67/repo/pinescripts/.venv/bin/python /home/rcaldwell67/repo/pinescripts/apm_v4_alpaca_paper_trader.py
#
# To maximize net return, additional logic added:
# - Trailing stop: activates once price moves ATR×4 in favor, trail stays ATR×1.5 from best price
# - Session gating: entries only 09:00–14:00 ET
# - Max bars exit: position closed after 24 bars (12 hours)
df = pd.read_json(data_path)
df['EMA_FAST'] = df['Close'].ewm(span=21, adjust=False).mean()
df['EMA_MID'] = df['Close'].ewm(span=50, adjust=False).mean()
df['EMA_SLOW'] = df['Close'].ewm(span=200, adjust=False).mean()
df['ATR'] = df['High'] - df['Low']
df['VOL_MA'] = df['Volume'].rolling(20).mean()
df['ADX'] = df['High'] - df['Low']  # Placeholder

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
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

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
    req = CryptoBarsRequest(symbols=[SYMBOL], timeframe=TIMEFRAME, start=start, end=end)
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
