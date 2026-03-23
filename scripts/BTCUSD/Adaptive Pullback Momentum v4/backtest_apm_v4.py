"""
backtest_apm_v4.py — Historical backtest for Adaptive Pullback Momentum v4 (BTCUSD)

Simulates trades bar-by-bar over historical data (no live API calls).
Outputs summary performance metrics at the end.
"""


import os
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

# Parameters (match v4.2 logic)
EMA_FAST   = 21;  EMA_MID  = 50;  EMA_SLOW = 200
ADX_LEN    = 14;  RSI_LEN  = 14;  ATR_LEN  = 14;  VOL_LEN = 20
ADX_THRESH = 25
PANIC_MULT = 1.3
ATR_FLOOR  = 0.002   # 0.20% of price
PB_TOL     = 0.0025  # 0.25% of EMA21
VOL_MULT   = 1.2
MIN_BODY   = 0.20
SLOPE_MIN_BARS = 3
RSI_LO_L = 42;  RSI_HI_L = 68
RSI_LO_S = 32;  RSI_HI_S = 58
SL_MULT    = 2.0
TP_MULT    = 3.5
TRAIL_ACT  = 2.5
TRAIL_DIST = 1.5
RISK_PCT   = 0.01
LEV_CAP    = 5.0
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
COOLDOWN_BARS = 0
MIN_BARS = EMA_SLOW + 60

def fetch_bars_alpaca(symbol="BTC/USD", days=365):
    api_key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("ALPACA_PAPER_API_SECRET") or os.environ.get("ALPACA_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("Missing Alpaca API credentials in environment variables.")
    client = CryptoHistoricalDataClient(api_key, api_secret)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    req = CryptoBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame(30, TimeFrameUnit.Minute),
        start=start,
        end=end,
    )
    bars = client.get_crypto_bars(req)
    df = bars.df.reset_index()
    df = df[df["symbol"] == symbol].copy()
    df = df.sort_values("timestamp").set_index("timestamp")
    df = df[["open", "high", "low", "close", "volume"]].rename(columns=str.title)
    df = df[df["Volume"] > 0].dropna()
    df.index = pd.to_datetime(df.index, utc=True)
    return df

# Compute indicators (same as v4.2)
def compute_indicators(df):
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
    dx = (100 * (d["DI_PLUS"] - d["DI_MINUS"]).abs() / (d["DI_PLUS"] + d["DI_MINUS"]).replace(0, 1e-10))
    d["ADX"] = dx.ewm(alpha=1 / ADX_LEN, adjust=False).mean()
    return d.dropna()

if __name__ == "__main__":
    # Load .env from project root and .venv
    dotenv_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env'),
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '.venv', '.env'),
    ]
    for path in dotenv_paths:
        if os.path.exists(path):
            load_dotenv(path, override=True)
    print("Fetching BTC/USD 30m bars from Alpaca...")
    df = fetch_bars_alpaca()
    print(f"Loaded {len(df)} bars from Alpaca.")
    df = compute_indicators(df)
    print(f"Indicators computed. Running parameter sweep...")

    from itertools import product
    sweep_results = []
    TP_MULT_range = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    SL_MULT_range = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
    TRAIL_ACT_range = [1.0, 1.5, 2.0, 2.5, 3.0]
    VOL_MULT_range = [0.5, 0.7, 1.0, 1.2]
    RISK_PCT_range = [0.01, 0.015, 0.02, 0.025, 0.03]
    SESSION_HOURS = [(0, 24), (6, 18), (9, 14)]

    for TP_MULT_, SL_MULT_, TRAIL_ACT_, VOL_MULT_, RISK_PCT_, (SESSION_START, SESSION_END) in product(
        TP_MULT_range, SL_MULT_range, TRAIL_ACT_range, VOL_MULT_range, RISK_PCT_range, SESSION_HOURS):
        equity = INITIAL_CAPITAL
        trades = []
        position = None
        cooldown = 0
        for i in range(MIN_BARS, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            idx = df.index[i]
            is_trending = row["ADX"] > ADX_THRESH
            is_panic = row["ATR"] > row["ATR_BL"] * PANIC_MULT
            atr_floor_ok = row["ATR"] / row["Close"] >= ATR_FLOOR
            et_hour = idx.tz_convert("America/New_York").hour
            in_session = SESSION_START <= et_hour < SESSION_END
            pb_tol_up = prev["EMA_FAST"] * (1.0 + PB_TOL)
            pb_tol_dn = prev["EMA_FAST"] * (1.0 - PB_TOL)
            body_size = abs(row["Close"] - row["Open"]) / row["ATR"] if row["ATR"] else 0
            long_pb = prev["Low"] <= pb_tol_up and row["Close"] > row["EMA_FAST"] and row["Close"] > row["Open"] and body_size >= MIN_BODY
            short_pb = prev["High"] >= pb_tol_dn and row["Close"] < row["EMA_FAST"] and row["Close"] < row["Open"] and body_size >= MIN_BODY
            ema_bull_full = row["EMA_FAST"] > row["EMA_MID"] > row["EMA_SLOW"]
            ema_bear_full = row["EMA_FAST"] < row["EMA_MID"] < row["EMA_SLOW"]
            ema_slope_up = row["EMA_FAST"] > df.iloc[i-SLOPE_MIN_BARS]["EMA_FAST"]
            ema_slope_down = row["EMA_FAST"] < df.iloc[i-SLOPE_MIN_BARS]["EMA_FAST"]
            rsi_rising = row["RSI"] > prev["RSI"]
            rsi_falling = row["RSI"] < prev["RSI"]
            vol_ok = row["Volume"] >= row["VOL_MA"] * VOL_MULT_
            long_ok = (not position and not is_panic and is_trending and atr_floor_ok and in_session and long_pb and ema_bull_full and ema_slope_up and rsi_rising and RSI_LO_L <= row["RSI"] <= RSI_HI_L and vol_ok)
            short_ok = (not position and not is_panic and is_trending and atr_floor_ok and in_session and short_pb and ema_bear_full and ema_slope_down and rsi_falling and RSI_LO_S <= row["RSI"] <= RSI_HI_S and vol_ok)
            stop_dist = row["ATR"] * SL_MULT_
            risk_qty = equity * RISK_PCT_ / stop_dist if stop_dist > 0 else 0
            max_qty = equity * LEV_CAP / row["Close"] if row["Close"] > 0 else 0
            entry_qty = min(risk_qty, max_qty)
            if position:
                if position["side"] == "long":
                    best = max(position["best"], row["High"])
                    position["best"] = best
                    if not position["trail_active"] and best >= position["entry"] + row["ATR"] * TRAIL_ACT_:
                        position["trail_active"] = True
                    if position["trail_active"]:
                        trail_sl = best - row["ATR"] * TRAIL_DIST
                        position["sl"] = max(position["sl"], trail_sl)
                    if row["Low"] <= position["sl"]:
                        exit_price = position["sl"]
                        result = "SL" if exit_price < position["tp"] else "Trail"
                    elif row["High"] >= position["tp"]:
                        exit_price = position["tp"]
                        result = "TP"
                    else:
                        continue
                else:
                    best = min(position["best"], row["Low"])
                    position["best"] = best
                    if not position["trail_active"] and best <= position["entry"] - row["ATR"] * TRAIL_ACT_:
                        position["trail_active"] = True
                    if position["trail_active"]:
                        trail_sl = best + row["ATR"] * TRAIL_DIST
                        position["sl"] = min(position["sl"], trail_sl)
                    if row["High"] >= position["sl"]:
                        exit_price = position["sl"]
                        result = "SL" if exit_price > position["tp"] else "Trail"
                    elif row["Low"] <= position["tp"]:
                        exit_price = position["tp"]
                        result = "TP"
                    else:
                        continue
                entry = position["entry"]
                qty = position["qty"]
                side = position["side"]
                notional = qty * entry
                if side == "long":
                    pnl = (exit_price - entry) / entry
                else:
                    pnl = (entry - exit_price) / entry
                dp = pnl * notional - notional * COMMISSION_PCT * 2
                equity += dp
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": idx,
                    "direction": side,
                    "entry": entry,
                    "exit": exit_price,
                    "result": result,
                    "pnl_pct": round(pnl * 100, 3),
                    "dollar_pnl": round(dp, 2),
                    "equity": round(equity, 2),
                })
                position = None
                cooldown = COOLDOWN_BARS
                continue
            if cooldown > 0:
                cooldown -= 1
                continue
            if long_ok and entry_qty > 0:
                position = {
                    "side": "long",
                    "entry": row["Close"],
                    "qty": entry_qty,
                    "entry_time": idx,
                    "sl": row["Close"] - row["ATR"] * SL_MULT_,
                    "tp": row["Close"] + row["ATR"] * TP_MULT_,
                    "best": row["Close"],
                    "trail_active": False,
                }
            elif short_ok and entry_qty > 0:
                position = {
                    "side": "short",
                    "entry": row["Close"],
                    "qty": entry_qty,
                    "entry_time": idx,
                    "sl": row["Close"] + row["ATR"] * SL_MULT_,
                    "tp": row["Close"] - row["ATR"] * TP_MULT_,
                    "best": row["Close"],
                    "trail_active": False,
                }
        if trades:
            wins = sum(1 for t in trades if t["dollar_pnl"] > 0)
            win_rate = wins / len(trades) * 100
            net_return = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
            sweep_results.append({
                "TP_MULT": TP_MULT_,
                "SL_MULT": SL_MULT_,
                "TRAIL_ACT": TRAIL_ACT_,
                "VOL_MULT": VOL_MULT_,
                "RISK_PCT": RISK_PCT_,
                "SESSION": f"{SESSION_START}-{SESSION_END}",
                "trades": len(trades),
                "win_rate": win_rate,
                "net_return": net_return,
            })
    sweep_results.sort(key=lambda x: x["net_return"], reverse=True)
    print("\nTop parameter sets by net return:")
    for res in sweep_results[:15]:
        print(f"TP={res['TP_MULT']}, SL={res['SL_MULT']}, TRAIL_ACT={res['TRAIL_ACT']}, VOL_MULT={res['VOL_MULT']}, RISK={res['RISK_PCT']*100:.1f}%, SESSION={res['SESSION']} | Trades={res['trades']} | Win%={res['win_rate']:.1f} | NetRet={res['net_return']:.2f}%")
