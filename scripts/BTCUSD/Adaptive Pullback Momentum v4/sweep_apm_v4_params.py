"""
sweep_apm_v4_params.py — Parameter sweep for APM v4 BTCUSD 30m strategy

This script automates the search for parameter sets that achieve +20% net return YTD.
"""

import itertools
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# --- Parameter grid ---
RISK_PCTS   = [0.01, 0.02, 0.03, 0.04]
SL_MULTS    = [1.5, 2.0, 2.5]
TP_MULTS    = [2.0, 2.5, 3.0, 3.5]
VOL_MULTS   = [1.0, 1.2]
MIN_BODIES  = [0.15, 0.20]
ATR_FLOORS  = [0.001, 0.0015, 0.002]
PANIC_MULTS = [1.3, 1.5]

# --- Fixed config ---
TICKER   = "BTC-USD"
INTERVAL = "30m"
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
YTD_START = f"{datetime.now().year}-01-01"

# --- Download YTD data ---
df = yf.download(TICKER, start=YTD_START, interval=INTERVAL, auto_adjust=True, progress=False)
df.columns = df.columns.get_level_values(0)
df.index   = pd.to_datetime(df.index, utc=True)
df.sort_index(inplace=True)

# --- Indicator functions (copied from backtest_apm_v4_improved.py) ---
def ema(s, n):     return s.ewm(span=n, adjust=False).mean()
def sma(s, n):     return s.rolling(n).mean()
def rsi_calc(s, n):
    d  = s.diff()
    g  = d.clip(lower=0).rolling(n).mean()
    ls = (-d).clip(lower=0).rolling(n).mean()
    return 100 - 100 / (1 + g / ls.replace(0, np.nan))
def atr_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()
def adx_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    up  = h.diff(); dn = -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr  = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    at  = tr.rolling(n).mean()
    pdi = pd.Series(pdm, index=h.index).rolling(n).mean() / at * 100
    ndi = pd.Series(ndm, index=h.index).rolling(n).mean() / at * 100
    dx  = ((pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan) * 100)
    return pdi, ndi, dx.rolling(n).mean()

# --- Sweep ---
results = []
for (risk_pct, sl_mult, tp_mult, vol_mult, min_body, atr_floor, panic_mult) in itertools.product(
    RISK_PCTS, SL_MULTS, TP_MULTS, VOL_MULTS, MIN_BODIES, ATR_FLOORS, PANIC_MULTS
):
    d = df.copy()
    d["EMA_FAST"] = ema(d["Close"], 21)
    d["EMA_MID"]  = ema(d["Close"], 50)
    d["EMA_SLOW"] = ema(d["Close"], 200)
    d["RSI"]      = rsi_calc(d["Close"], 14)
    d["ATR"]      = atr_calc(d, 14)
    d["ATR_BL"]   = sma(d["ATR"], 60)
    d["VOL_MA"]   = sma(d["Volume"], 20)
    d["DI_PLUS"], d["DI_MINUS"], d["ADX"] = adx_calc(d, 14)
    d.dropna(inplace=True)

    # Entry/exit logic (simplified for sweep)
    equity = INITIAL_CAPITAL
    position = None
    entry_price = 0
    for i in range(3, len(d)):
        row = d.iloc[i]
        prev = d.iloc[i-1]
        # Example: only long entries for brevity
        # Add full logic for both directions as needed
        # --- Entry conditions (simplified) ---
        if not position:
            ema_bull = row["EMA_FAST"] > row["EMA_MID"] > row["EMA_SLOW"]
            ema_slope = row["EMA_FAST"] > d.iloc[i-3]["EMA_FAST"]
            rsi_rising = row["RSI"] > prev["RSI"]
            vol_ok = row["Volume"] >= row["VOL_MA"] * vol_mult
            atr_ok = row["ATR"] / row["Close"] >= atr_floor
            body = abs(row["Close"] - row["Open"]) / row["ATR"]
            if all([ema_bull, ema_slope, rsi_rising, vol_ok, atr_ok, body >= min_body]):
                stop_dist = row["ATR"] * sl_mult
                qty = equity * risk_pct / stop_dist
                entry_price = row["Close"]
                position = {"qty": qty, "entry": entry_price, "sl": entry_price - stop_dist, "tp": entry_price + row["ATR"] * tp_mult}
        else:
            # --- Exit logic (TP/SL) ---
            if row["Low"] <= position["sl"]:
                pnl = (position["sl"] - position["entry"]) * position["qty"] - equity * COMMISSION_PCT
                equity += pnl
                position = None
            elif row["High"] >= position["tp"]:
                pnl = (position["tp"] - position["entry"]) * position["qty"] - equity * COMMISSION_PCT
                equity += pnl
                position = None
    net_return = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    results.append({
        "risk_pct": risk_pct, "sl_mult": sl_mult, "tp_mult": tp_mult,
        "vol_mult": vol_mult, "min_body": min_body, "atr_floor": atr_floor,
        "panic_mult": panic_mult, "net_return": net_return
    })

# --- Output results ---
results_df = pd.DataFrame(results)
results_df = results_df.sort_values("net_return", ascending=False)
results_df[results_df["net_return"] >= 20].to_csv("sweep_apm_v4_results.csv", index=False)
print("Sweep complete. Top results saved to sweep_apm_v4_results.csv")
