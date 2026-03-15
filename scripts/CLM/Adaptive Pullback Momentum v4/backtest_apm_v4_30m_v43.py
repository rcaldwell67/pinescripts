# ─────────────────────────────────────────────────────────────────────────────
# APM v4.3 — CLM 30m  ·  12-Month Final Backtest  (Alpaca IEX)
# Mirrors "Adaptive Pullback Momentum v4.3" Pine defaults exactly.
#
# Data: Alpaca IEX 5m bars → resampled to 30m
# Period: 2025-03-14 → 2026-03-14  (12 months)
#
# v4.3 best config (S7 trail-dist sweep):
#   trail_act=2.5, trail_dist=0.3, tp=16, adx=10, sl=1.5, risk=3%
#   PB=0.50%, VOL=1.2, RSI_S=(30,62), RSI_L=(38,68), MIN_BODY=0.15
#   EMA_SLOPE=True, RSI_DIR=True, Longs+Shorts both on
#   → n=51, WR=47.1%, PF=1.417, ret=+23.71%, MDD=-12.75%, Calmar=1.86
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["alpaca-py", "pandas", "numpy", "matplotlib", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import os
import pandas as pd
import numpy as np
import pytz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

_ET = pytz.timezone("America/New_York")

ALPACA_KEY    = os.environ.get("ALPACA_PAPER_API_KEY",    "PKNIYXYVLHKHF43IIEUQIA42DJ")
ALPACA_SECRET = os.environ.get("ALPACA_PAPER_API_SECRET", "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u")

TICKER          = "CLM"
BACKTEST_START  = datetime(2025, 3, 14, tzinfo=timezone.utc)
BACKTEST_END    = datetime(2026, 3, 14, tzinfo=timezone.utc)
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006

EMA_FAST = 21;  EMA_MID = 50;  EMA_SLOW = 200
ADX_LEN  = 14;  RSI_LEN = 14;  ATR_LEN  = 14
VOL_LEN  = 20;  ATR_BL_LEN = 60

# ── APM v4.3 parameters (matches Pine Script v4.3 defaults) ──────────────────
ADX_THRESH   = 10
PB_PCT       = 0.50
VOL_MULT     = 1.2
MIN_BODY     = 0.15
ATR_FLOOR    = 0.001
SL_MULT      = 1.5
TP_MULT      = 16.0
TRAIL_ACT    = 2.5
TRAIL_DIST   = 0.3
PANIC_MULT   = 1.5
RISK_PCT     = 0.03

RSI_LO_S = 30;  RSI_HI_S = 62
RSI_LO_L = 38;  RSI_HI_L = 68

EMA_SLOPE = True
RSI_DIR   = True
TRADE_LONGS  = True
TRADE_SHORTS = True

# ─── Download 5m → resample 30m ──────────────────────────────────────────────
print(f"Downloading {TICKER} 5m via Alpaca ({BACKTEST_START.date()} → {BACKTEST_END.date()}) ...")
client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
req = StockBarsRequest(
    symbol_or_symbols=TICKER,
    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
    start=BACKTEST_START, end=BACKTEST_END, feed=DataFeed.IEX,
)
bars = client.get_stock_bars(req)
raw  = bars.df.reset_index()
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(0)
raw = raw.rename(columns={"timestamp": "time"}).set_index("time")
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw = raw[["open","high","low","close","volume"]].rename(columns=str.title)
raw = raw[raw["Volume"] > 0].dropna()
print(f"  raw 5m bars: {len(raw)}")

raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample("30min", label="left", closed="left", origin="start_day").agg(
    {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"})
df = df[df["Volume"] > 0].dropna()
print(f"  30m bars: {len(df)}  |  {df.index[0]}..{df.index[-1]}")

# ─── Indicators ──────────────────────────────────────────────────────────────
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta = df["Close"].diff()
avg_g = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - 100 / (1 + avg_g / avg_l.replace(0, 1e-10))

hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift()).abs()
lpc = (df["Low"]  - df["Close"].shift()).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up   = df["High"] - df["High"].shift()
dn   = df["Low"].shift() - df["Low"]
pdm  = np.where((up > dn) & (up > 0), up, 0.0)
ndm  = np.where((dn > up) & (dn > 0), dn, 0.0)
sp   = pd.Series(pdm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
sn   = pd.Series(ndm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * sp / df["ATR"]
df["DI_MINUS"] = 100 * sn / df["ATR"]
dx   = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10)
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()

df.dropna(inplace=True)
print(f"  bars after warmup: {len(df)}")

# ─── Signal components ────────────────────────────────────────────────────────
tol       = PB_PCT / 100.0
body_size = (df["Close"] - df["Open"]).abs() / df["ATR"]

is_trending  = df["ADX"] > ADX_THRESH
is_panic     = df["ATR"] > df["ATR_BL"] * PANIC_MULT
atr_floor_ok = df["ATR"] / df["Close"] >= ATR_FLOOR

ema_bull = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_bear = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])

ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)

pb_tol_up = df["EMA_FAST"].shift(1) * (1.0 + tol)
pb_tol_dn = df["EMA_FAST"].shift(1) * (1.0 - tol)

long_pb  = ((df["Low"].shift(1)  <= pb_tol_up) & (df["Close"] > df["EMA_FAST"])
             & (df["Close"] > df["Open"]) & (body_size >= MIN_BODY))
short_pb = ((df["High"].shift(1) >= pb_tol_dn) & (df["Close"] < df["EMA_FAST"])
             & (df["Close"] < df["Open"]) & (body_size >= MIN_BODY))

rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)
rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
vol_ok = df["Volume"] >= df["VOL_MA"] * VOL_MULT

long_signal = (
    pd.Series([TRADE_LONGS] * len(df), index=df.index)
    & long_pb & ema_bull
    & (ema_slope_up   if EMA_SLOPE else True)
    & (rsi_rising     if RSI_DIR   else True)
    & rsi_long_ok & vol_ok & atr_floor_ok & is_trending & ~is_panic
)
short_signal = (
    pd.Series([TRADE_SHORTS] * len(df), index=df.index)
    & short_pb & ema_bear
    & (ema_slope_down if EMA_SLOPE else True)
    & (rsi_falling    if RSI_DIR   else True)
    & rsi_short_ok & vol_ok & atr_floor_ok & is_trending & ~is_panic
)

print(f"\nSignals — Long: {long_signal.sum()}  Short: {short_signal.sum()}")

# ─── Bar-by-bar simulation ────────────────────────────────────────────────────
equity  = INITIAL_CAPITAL
pos     = None
trades  = []
eqcurve = []

for ts, row in df.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])
    sd    = atr * SL_MULT

    htp = hsl = False
    if pos is not None:
        d = pos["direction"]
        if d == "long":
            if high > pos["best"]: pos["best"] = high
            if pos["best"] >= pos["trail_activate_px"]:
                pos["sl"] = max(pos["sl"], pos["best"] - pos["trail_dist_fixed"])
            htp = high >= pos["tp"]
            hsl = low  <= pos["sl"]
        else:
            if low < pos["best"]: pos["best"] = low
            if pos["best"] <= pos["trail_activate_px"]:
                pos["sl"] = min(pos["sl"], pos["best"] + pos["trail_dist_fixed"])
            htp = low  <= pos["tp"]
            hsl = high >= pos["sl"]

    if htp or hsl:
        d  = pos["direction"]
        xp = pos["tp"] if htp else pos["sl"]
        pnl = ((xp - pos["entry"]) / pos["entry"] if d == "long"
               else (pos["entry"] - xp) / pos["entry"])
        dp = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
        equity += dp
        trades.append({
            "entry_time": pos["entry_time"], "exit_time": ts,
            "direction": d, "entry": pos["entry"], "exit": xp,
            "result": "TP" if htp else "SL",
            "pnl_pct": round(pnl * 100, 3),
            "dollar_pnl": round(dp, 2), "equity": round(equity, 2),
        })
        pos = None

    if pos is None:
        sig = "long" if bool(long_signal[ts]) else "short" if bool(short_signal[ts]) else None
        if sig:
            sl  = close - sd if sig == "long" else close + sd
            tp  = close + atr * TP_MULT if sig == "long" else close - atr * TP_MULT
            tap = close + atr * TRAIL_ACT if sig == "long" else close - atr * TRAIL_ACT
            stop_dist = abs(close - sl)
            notl = min(equity * RISK_PCT / stop_dist * close, equity * 5.0)
            pos = {
                "direction": sig, "entry": close, "entry_time": ts,
                "sl": sl, "tp": tp, "best": close, "notional": notl,
                "trail_activate_px": tap, "trail_dist_fixed": atr * TRAIL_DIST,
            }

    eqcurve.append({"time": ts, "equity": equity})

print(f"\nSimulation complete. Trades: {len(trades)}")

# ─── Statistics ──────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)
if tdf.empty:
    print("No trades."); sys.exit(0)

wins   = tdf[tdf["dollar_pnl"] > 0]
losses = tdf[tdf["dollar_pnl"] <= 0]
final  = tdf["equity"].iloc[-1]
total  = tdf["dollar_pnl"].sum()
wr     = len(wins) / len(tdf) * 100
gp     = wins["dollar_pnl"].sum()   if not wins.empty   else 0.0
gl     = losses["dollar_pnl"].sum() if not losses.empty else 0.0
pf     = gp / abs(gl) if gl != 0 else float("inf")
tp_cnt = (tdf["result"] == "TP").sum()
sl_cnt = (tdf["result"] == "SL").sum()
lng_c  = (tdf["direction"] == "long").sum()
sht_c  = (tdf["direction"] == "short").sum()
ret    = (final / INITIAL_CAPITAL - 1) * 100

eq_s   = pd.Series([e["equity"] for e in eqcurve])
mdd    = ((eq_s - eq_s.cummax()) / eq_s.cummax() * 100).min()
calmar = ret / abs(mdd) if mdd != 0 else float("inf")

print("=" * 60)
print(f"  APM v4.3  —  {TICKER} 30m  (12 months, Alpaca IEX)")
print("=" * 60)
print(f"  Initial capital   :  ${INITIAL_CAPITAL:>10,.2f}")
print(f"  Final equity      :  ${final:>10,.2f}")
print(f"  Net P&L           : ${total:>+11,.2f}")
print(f"  Return            : {ret:>+10.2f} %")
print(f"  Max drawdown      : {mdd:>10.2f} %")
print(f"  Calmar ratio      : {calmar:>10.2f}")
print(f"  Profit factor     : {pf:>10.3f}")
print("-" * 60)
print(f"  Total trades      : {len(tdf):>5}  (L:{lng_c} S:{sht_c})")
print(f"  TP exits          : {tp_cnt:>5}")
print(f"  SL exits          : {sl_cnt:>5}")
print(f"  Win rate          : {wr:>9.1f} %")
print("=" * 60)

for _, t in tdf.iterrows():
    print(f"  {str(t['entry_time'])[:16]}  {t['direction']:<5}  "
          f"entry={t['entry']:.4f}  exit={t['exit']:.4f}  "
          f"{t['result']}  {t['pnl_pct']:+.2f}%  dp={t['dollar_pnl']:+.2f}  eq={t['equity']:.2f}")

out_csv = f"apm_v4_v43_trades_{TICKER.lower()}_30m.csv"
tdf.to_csv(out_csv, index=False)
print(f"\nTrades CSV → {out_csv}")

# ─── Chart ────────────────────────────────────────────────────────────────────
ec_df = pd.DataFrame(eqcurve).set_index("time")
plt.style.use("dark_background")
fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(ec_df.index, ec_df["equity"], color="#63b3ed", linewidth=1.5)
ax.axhline(INITIAL_CAPITAL, color="#718096", linewidth=0.8, linestyle="--")
ax.fill_between(ec_df.index, ec_df["equity"], INITIAL_CAPITAL,
                where=ec_df["equity"] >= INITIAL_CAPITAL, alpha=0.15, color="#48bb78")
ax.fill_between(ec_df.index, ec_df["equity"], INITIAL_CAPITAL,
                where=ec_df["equity"] < INITIAL_CAPITAL, alpha=0.20, color="#fc8181")
ax.set_title(
    f"APM v4.3 (CLM 30m)  ·  12-Month Alpaca IEX  ·  "
    f"Return {ret:+.2f}%  WR={wr:.0f}%  MDD={mdd:.2f}%  PF={pf:.3f}",
    color="white", fontsize=10)
ax.set_xlabel("Date"); ax.set_ylabel("Equity ($)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
ax.xaxis.set_major_locator(mdates.MonthLocator())
plt.xticks(rotation=30); plt.tight_layout()
out_png = f"apm_v4_v43_equity_{TICKER.lower()}_30m.png"
plt.savefig(out_png, dpi=130, bbox_inches="tight")
plt.close()
print(f"Chart → {out_png}")
