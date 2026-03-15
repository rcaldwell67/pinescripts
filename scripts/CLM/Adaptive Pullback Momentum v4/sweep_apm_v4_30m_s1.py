# ─────────────────────────────────────────────────────────────────────────────
# APM v4.2 — CLM 30m — Stage 1 parameter sweep  (12 months, Alpaca IEX)
#
# Goal: net profit > 20% on 1-year Alpaca data.
#
# Baseline (v4.2 CLM defaults): -2.18%  WR=37.5%  8 trades
#   Key bottleneck: adx_rising cuts 36→16 signals (55% removal)
#
# Sweep grid (216 combos):
#   ADX_THRESH      : [10, 12, 14]
#   ADX_SLOPE_BARS  : [0 (off), 1]     ← biggest filter impact
#   DI_SPREAD_MIN   : [0.0, 2.0, 4.0]
#   TP_MULT         : [4.0, 5.0, 6.0]
#   RISK_PCT        : [1%, 1.5%, 2%, 2.5%]
#
# Fixed across sweep:
#   SL_MULT=2.0, PB_PCT=0.30, VOL_MULT=0.50, MIN_BODY=0.15
#   ATR_FLOOR=0.0010, PANIC_MULT=1.5, RSI_LO_S=30, RSI_HI_S=62
#   MOMENTUM_BARS=5, CONSEC_LOSS CD enabled
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["alpaca-py", "pandas", "numpy"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import os
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed
import pytz

_ET = pytz.timezone("America/New_York")

ALPACA_KEY    = os.environ.get("ALPACA_PAPER_API_KEY",    "PKNIYXYVLHKHF43IIEUQIA42DJ")
ALPACA_SECRET = os.environ.get("ALPACA_PAPER_API_SECRET", "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u")

TICKER          = "CLM"
BACKTEST_START  = datetime(2025, 3, 14, tzinfo=timezone.utc)
BACKTEST_END    = datetime(2026, 3, 14, tzinfo=timezone.utc)
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006

# Fixed params
EMA_FAST   = 21;  EMA_MID   = 50;  EMA_SLOW  = 200
ADX_LEN    = 14;  RSI_LEN   = 14;  ATR_LEN   = 14
VOL_LEN    = 20;  ATR_BL_LEN = 60

PB_PCT         = 0.30
VOL_MULT       = 0.50
MIN_BODY       = 0.15
ATR_FLOOR      = 0.0010
PANIC_MULT     = 1.5
SL_MULT        = 2.0
TRAIL_ACT      = 99.0   # effectively disabled (hard TP only in sweep)
TRAIL_DIST     = 1.5
RSI_LO_S       = 30;  RSI_HI_S  = 62
MOMENTUM_BARS  = 5
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
TP_COOLDOWN_BARS     = 2
TRADE_SHORTS   = True
TRADE_LONGS    = False

# ── Sweep grid ─────────────────────────────────────────────────────────────
ADX_THRESH_RANGE   = [10, 12, 14]
ADX_SLOPE_RANGE    = [0, 1]          # 0 = off
DI_SPREAD_RANGE    = [0.0, 2.0, 4.0]
TP_RANGE           = [4.0, 5.0, 6.0]
RISK_RANGE         = [0.010, 0.015, 0.020, 0.025]

total = (len(ADX_THRESH_RANGE) * len(ADX_SLOPE_RANGE) * len(DI_SPREAD_RANGE)
         * len(TP_RANGE) * len(RISK_RANGE))
print(f"Combinations: {total}")

# ── Download once ────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} 5m via Alpaca ({BACKTEST_START.date()} → {BACKTEST_END.date()}) ...")
client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
req = StockBarsRequest(
    symbol_or_symbols=TICKER,
    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
    start=BACKTEST_START,
    end=BACKTEST_END,
    feed=DataFeed.IEX,
)
bars = client.get_stock_bars(req)
raw  = bars.df.reset_index()
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(0)
raw = raw.rename(columns={"timestamp": "time"}).set_index("time")
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw = raw[["open", "high", "low", "close", "volume"]].rename(columns=str.title)
raw = raw[raw["Volume"] > 0].dropna()

# ── Resample 5m → 30m ─────────────────────────────────────────────────────
raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample(
    "30min", label="left", closed="left", origin="start_day"
).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df = df[df["Volume"] > 0].dropna()
print(f"  30m bars: {len(df)}")

# ── Compute fixed indicators ─────────────────────────────────────────────
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta  = df["Close"].diff()
avg_g  = delta.clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
avg_l  = (-delta).clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1 / ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up_move  = df["High"] - df["High"].shift(1)
dn_move  = df["Low"].shift(1) - df["Low"]
plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
s_plus   = pd.Series(plus_dm,  index=df.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
s_minus  = pd.Series(minus_dm, index=df.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * s_plus  / df["ATR"]
df["DI_MINUS"] = 100 * s_minus / df["ATR"]
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
    (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1 / ADX_LEN, adjust=False).mean()
df.dropna(inplace=True)

# Stable components (independent of sweep params)
tol       = PB_PCT / 100.0
body_size = (df["Close"] - df["Open"]).abs() / df["ATR"]
is_panic  = df["ATR"] > df["ATR_BL"] * PANIC_MULT

ema_bear       = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
pb_tol_dn      = df["EMA_FAST"].shift(1) * (1.0 - tol)
short_pb       = ((df["High"].shift(1) >= pb_tol_dn) &
                  (df["Close"] < df["EMA_FAST"])       &
                  (df["Close"] < df["Open"])             &
                  (body_size >= MIN_BODY))

rsi_falling = df["RSI"] < df["RSI"].shift(1)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
vol_ok       = df["Volume"] >= df["VOL_MA"] * VOL_MULT
atr_floor_ok = df["ATR"] / df["Close"] >= ATR_FLOOR
momentum_ok_s = df["Close"] < df["Close"].shift(MOMENTUM_BARS)

di_spread_s_raw = df["DI_MINUS"] - df["DI_PLUS"]
adx_rising_1 = df["ADX"] > df["ADX"].shift(1)

# Base filter mask (stable across sweep)
base_short = (
    short_pb & ema_bear & ema_slope_down &
    rsi_falling & rsi_short_ok &
    vol_ok & atr_floor_ok &
    momentum_ok_s & ~is_panic
)

bar_arr = df.index.tolist()
bar_idx = {t: i for i, t in enumerate(bar_arr)}
close_a = df["Close"].values
high_a  = df["High"].values
low_a   = df["Low"].values
atr_a   = df["ATR"].values
adx_a   = df["ADX"].values

print(f"\nRunning {total} combinations...")

results = []
done    = 0

for adx_thresh in ADX_THRESH_RANGE:
    is_trending = df["ADX"] > adx_thresh

    for adx_slope_bars in ADX_SLOPE_RANGE:
        adx_slope_ok = (df["ADX"] > df["ADX"].shift(adx_slope_bars)
                        if adx_slope_bars > 0
                        else pd.Series([True] * len(df), index=df.index))

        for di_spread_min in DI_SPREAD_RANGE:
            di_ok = (di_spread_s_raw >= di_spread_min
                     if di_spread_min > 0
                     else pd.Series([True] * len(df), index=df.index))

            short_sig = base_short & is_trending & adx_slope_ok & di_ok
            sig_arr   = short_sig.values

            for tp_mult in TP_RANGE:
                for risk_pct in RISK_RANGE:
                    equity        = INITIAL_CAPITAL
                    pos           = None
                    n_trades      = 0
                    wins          = 0
                    gross_p       = 0.0
                    gross_l       = 0.0
                    min_eq        = INITIAL_CAPITAL
                    consec_losses = 0
                    cooldown      = 0

                    for i, ts in enumerate(bar_arr):
                        cl  = close_a[i]
                        hi  = high_a[i]
                        lo  = low_a[i]
                        av  = atr_a[i]
                        sd  = av * SL_MULT

                        htp = hsl = False
                        if pos is not None:
                            if pos["dir"] == "short":
                                if lo < pos["best"]:
                                    pos["best"] = lo
                                htp = lo <= pos["tp"]
                                hsl = hi >= pos["sl"]

                        if htp or hsl:
                            xp  = pos["tp"] if htp else pos["sl"]
                            pnl = (pos["entry"] - xp) / pos["entry"]
                            dp  = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                            equity += dp
                            n_trades += 1
                            if dp > 0:
                                wins += 1; gross_p += dp
                                cooldown = max(cooldown, TP_COOLDOWN_BARS)
                                consec_losses = 0
                            else:
                                gross_l += dp
                                consec_losses += 1
                                if consec_losses >= CONSEC_LOSS_LIMIT:
                                    cooldown = max(cooldown, CONSEC_LOSS_COOLDOWN)
                                    consec_losses = 0
                            if equity < min_eq:
                                min_eq = equity
                            pos = None

                        if pos is None:
                            if cooldown > 0:
                                cooldown -= 1
                            elif sig_arr[i]:
                                notl = min(equity * risk_pct / sd * cl, equity * 5.0)
                                pos  = {
                                    "dir":    "short",
                                    "entry":  cl,
                                    "sl":     cl + sd,
                                    "tp":     cl - av * tp_mult,
                                    "best":   cl,
                                    "notional": notl,
                                }

                    ret    = (equity / INITIAL_CAPITAL - 1) * 100
                    wr     = wins / n_trades * 100 if n_trades else 0.0
                    pf     = (gross_p / abs(gross_l)) if gross_l < 0 else (float("inf") if gross_p > 0 else 0.0)
                    mdd    = (min_eq / INITIAL_CAPITAL - 1) * 100
                    calmar = ret / abs(mdd) if mdd != 0 else float("inf")

                    results.append({
                        "adx_thresh":    adx_thresh,
                        "adx_slope":     adx_slope_bars,
                        "di_spread":     di_spread_min,
                        "tp":            tp_mult,
                        "risk":          risk_pct,
                        "n":             n_trades,
                        "wr":            round(wr, 1),
                        "pf":            round(pf, 3),
                        "ret":           round(ret, 2),
                        "mdd":           round(mdd, 2),
                        "calmar":        round(calmar, 2),
                    })
                    done += 1
                    if done % 50 == 0:
                        print(f"  {done}/{total}  best so far: {max(r['ret'] for r in results):+.2f}%")

rdf = pd.DataFrame(results).sort_values("ret", ascending=False)
out = "sweep_apm_v4_30m_s1.csv"
rdf.to_csv(out, index=False)
print(f"\nSweep done. Results → {out}")
print(f"\nTop 20 by net return (min 5 trades):")
top = rdf[rdf["n"] >= 5].head(20)
print(top.to_string(index=False))

print(f"\nTop 20 by Calmar (min 5 trades, ret>0):")
top_c = rdf[(rdf["n"] >= 5) & (rdf["ret"] > 0)].sort_values("calmar", ascending=False).head(20)
print(top_c.to_string(index=False))
