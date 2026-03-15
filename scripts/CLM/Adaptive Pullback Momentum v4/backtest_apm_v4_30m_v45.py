"""
APM v4.5  –  CLM 30-minute  –  MDD-constrained backtest
=========================================================
Params (S9 sweep winner):
  RISK_PCT    = 1.0 %   (below 5× leverage cap for most CLM trades)
  CB_DD_PCT   = 4.0 %   (equity-recovery circuit breaker trigger)
  TRAIL_DIST  = 0.1 ×ATR
  TRAIL_ACT   = 3.0 ×ATR
  SL          = 1.0 ×ATR
  TP          = 16.0 ×ATR (trail does exit work; TP is safety net)

Results  (2025-03-14 → 2026-03-14, CLM 30 min):
  Return  : +18.14 %
  MDD     : -4.17 %
  Calmar  : 4.35
  Trades  : 17
  WR      : 47.1 %
  PF      : 2.25
  Avg win : $408.42  |  Avg loss : $-161.48
"""

import os, sys
import pandas as pd
import numpy as np
import pytz
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

# ── Config ────────────────────────────────────────────────────────────────────
SYMBOL      = "CLM"
START       = datetime(2025, 3, 14, tzinfo=timezone.utc)
END         = datetime(2026, 3, 14, tzinfo=timezone.utc)
INIT_EQ     = 10_000.0
COMMISSION  = 0.0006          # 0.06 % per side
LEV_CAP     = 5.0             # maximum leverage

# v4.5 strategy params
RISK_PCT    = 0.010           # 1.0 % of equity risked per trade
CB_DD_PCT   = 4.0             # circuit breaker: halt when DD > 4 % from HWM
SL_MULT     = 1.0
TP_MULT     = 16.0
TRAIL_ACT   = 3.0             # trail activates after 3×ATR move in favour
TRAIL_DIST  = 0.1             # trail stays 0.1×ATR from best price

# indicator params (unchanged from v4.4)
EMA_FAST    = 21
EMA_MID     = 50
EMA_SLOW    = 200
RSI_LEN     = 14
ATR_LEN     = 14
ADX_LEN     = 14
VOL_LEN     = 20
VOL_MULT    = 1.0
ADX_THRESH  = 10
PANIC_MULT  = 1.5
PB_TOL      = 0.005           # 0.50 %
ATR_FLOOR   = 0.001           # 0.10 %
RSI_LO_L    = 38; RSI_HI_L = 68
RSI_LO_S    = 30; RSI_HI_S = 62
MIN_BODY    = 0.15
_ET         = pytz.timezone("America/New_York")

# ── Fetch data ────────────────────────────────────────────────────────────────
ALPACA_KEY    = os.environ.get("ALPACA_PAPER_API_KEY",    "PKNIYXYVLHKHF43IIEUQIA42DJ")
ALPACA_SECRET = os.environ.get("ALPACA_PAPER_API_SECRET", "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u")

print(f"Fetching {SYMBOL} 5-min bars …")
client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
req  = StockBarsRequest(
    symbol_or_symbols=SYMBOL,
    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
    start=START, end=END, feed=DataFeed.IEX)
raw = client.get_stock_bars(req).df.reset_index()
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(0)
raw = raw.rename(columns={"timestamp": "time"}).set_index("time")
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw = raw[["open", "high", "low", "close", "volume"]].rename(columns=str.title)
raw = raw[raw["Volume"] > 0].dropna()
raw.index = raw.index.tz_convert(_ET)

# resample to 30-minute bars
df = raw.resample("30min", label="left", closed="left", origin="start_day").agg(
    {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df = df[df["Volume"] > 0].dropna()
print(f"30-min bars: {len(df)}")

# ── Indicators ────────────────────────────────────────────────────────────────
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta  = df["Close"].diff()
avg_g  = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l  = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - 100 / (1 + avg_g / avg_l.replace(0, 1e-10))

hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift()).abs()
lpc = (df["Low"]  - df["Close"].shift()).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(60).mean()
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up  = df["High"] - df["High"].shift()
dn  = df["Low"].shift() - df["Low"]
pdm = np.where((up > dn) & (up > 0), up, 0.0)
ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
sp  = pd.Series(pdm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
sn  = pd.Series(ndm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * sp / df["ATR"]
df["DI_MINUS"] = 100 * sn / df["ATR"]
dx  = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
      (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()
df.dropna(inplace=True)

# ── Signal generation ─────────────────────────────────────────────────────────
body_size   = (df["Close"] - df["Open"]).abs() / df["ATR"]
is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT
atr_fl_ok   = df["ATR"] / df["Close"] >= ATR_FLOOR

ema_bull = (df["EMA_FAST"] > df["EMA_MID"])  & (df["EMA_MID"]  > df["EMA_SLOW"])
ema_bear = (df["EMA_FAST"] < df["EMA_MID"])  & (df["EMA_MID"]  < df["EMA_SLOW"])
ema_su   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_sd   = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
rsi_r    = df["RSI"] > df["RSI"].shift(1)
rsi_f    = df["RSI"] < df["RSI"].shift(1)
rsi_lo_l = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_lo_s = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
pb_up    = df["EMA_FAST"].shift(1) * (1 + PB_TOL)
pb_dn    = df["EMA_FAST"].shift(1) * (1 - PB_TOL)
vol_ok   = df["Volume"] >= df["VOL_MA"] * VOL_MULT
body_ok  = body_size >= MIN_BODY

long_pb  = (df["Low"].shift(1)  <= pb_up) & (df["Close"] > df["EMA_FAST"]) & (df["Close"] > df["Open"])  & body_ok
short_pb = (df["High"].shift(1) >= pb_dn) & (df["Close"] < df["EMA_FAST"]) & (df["Close"] < df["Open"]) & body_ok

ls = long_pb  & ema_bull & ema_su & rsi_r & rsi_lo_l & vol_ok & atr_fl_ok & is_trending & ~is_panic
ss = short_pb & ema_bear & ema_sd & rsi_f & rsi_lo_s & vol_ok & atr_fl_ok & is_trending & ~is_panic

# ── Simulation (bar-by-bar, equity-recovery circuit breaker) ──────────────────
equity  = INIT_EQ
hwm     = INIT_EQ       # high-water mark for circuit breaker
halted  = False         # circuit breaker state
pos     = None
trades  = []

for ts, row in df.iterrows():
    c = float(row["Close"]); h = float(row["High"])
    lo = float(row["Low"]);  a = float(row["ATR"])

    # update HWM
    if equity > hwm:
        hwm = equity

    # circuit breaker logic
    # HALT when equity falls CB_DD_PCT% below HWM
    if not halted and (equity - hwm) / hwm * 100 <= -CB_DD_PCT:
        halted = True
    # RESUME when equity recovers halfway back to HWM
    if halted and equity >= hwm * (1 - CB_DD_PCT / 200):
        halted = False
        hwm = equity     # reset HWM on resume to avoid immediate re-trigger

    # manage open position (trail stop)
    htp = hsl = False
    if pos is not None:
        d = pos["d"]
        if d == "long":
            if h > pos["best"]:
                pos["best"] = h
            if pos["best"] >= pos["tap"]:
                pos["sl"] = max(pos["sl"], pos["best"] - pos["td"])
            htp = h  >= pos["tp"]
            hsl = lo <= pos["sl"]
        else:
            if lo < pos["best"]:
                pos["best"] = lo
            if pos["best"] <= pos["tap"]:
                pos["sl"] = min(pos["sl"], pos["best"] + pos["td"])
            htp = lo <= pos["tp"]
            hsl = h  >= pos["sl"]

    # close position
    if htp or hsl:
        xp  = pos["tp"] if htp else pos["sl"]
        pnl = (xp - pos["e"]) / pos["e"] if pos["d"] == "long" else (pos["e"] - xp) / pos["e"]
        dp  = pnl * pos["n"] - 2 * COMMISSION * pos["n"]
        equity += dp
        trades.append({
            "ts":       str(ts)[:16],
            "dir":      pos["d"],
            "entry":    round(pos["e"], 4),
            "exit":     round(xp, 4),
            "reason":   "TP" if htp else "TSL",
            "pnl_pct":  round(pnl * 100, 3),
            "dp":       round(dp, 2),
            "equity":   round(equity, 2),
        })
        pos = None

    # open new position (only when not circuit-breaker halted)
    if pos is None and not halted:
        sig = "long" if bool(ls[ts]) else "short" if bool(ss[ts]) else None
        if sig:
            sl  = c - a if sig == "long" else c + a
            tp  = c + a * TP_MULT if sig == "long" else c - a * TP_MULT
            tap = c + a * TRAIL_ACT if sig == "long" else c - a * TRAIL_ACT
            sd  = abs(c - sl)
            n   = min(equity * RISK_PCT / sd * c, equity * LEV_CAP)
            pos = {"d": sig, "e": c, "sl": sl, "tp": tp,
                   "best": c, "n": n, "tap": tap, "td": a * TRAIL_DIST}

# ── Results ───────────────────────────────────────────────────────────────────
tdf    = pd.DataFrame(trades)
eq_s   = tdf["equity"]
wins   = tdf[tdf["dp"] > 0]
losses = tdf[tdf["dp"] <= 0]

ret    = (equity / INIT_EQ - 1) * 100
mdd    = ((eq_s - eq_s.cummax()) / eq_s.cummax() * 100).min()
calmar = ret / abs(mdd) if mdd else 0
wr     = len(wins) / len(tdf) * 100
pf     = wins["dp"].sum() / abs(losses["dp"].sum()) if len(losses) and losses["dp"].sum() != 0 else float("inf")

print()
print("=" * 56)
print(f"  APM v4.5  |  {SYMBOL} 30m  |  {START.date()} → {END.date()}")
print("=" * 56)
print(f"  Return    : {ret:+.2f}%")
print(f"  MDD       : {mdd:.2f}%")
print(f"  Calmar    : {calmar:.2f}")
print(f"  Trades    : {len(tdf)}")
print(f"  Win rate  : {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
print(f"  Prof fact : {pf:.2f}")
print(f"  Avg win   : ${wins['dp'].mean():.2f}")
print(f"  Avg loss  : ${losses['dp'].mean():.2f}")
print(f"  Final eq  : ${equity:.2f}")
print("=" * 56)
print()
print(tdf.to_string(index=False))

out = "apm_v4_v45_trades_clm_30m.csv"
tdf.to_csv(out, index=False)
print(f"\nSaved: {out}")
