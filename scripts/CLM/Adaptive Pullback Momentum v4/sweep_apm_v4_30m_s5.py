# ─────────────────────────────────────────────────────────────────────────────
# APM v4 — CLM 10m — Stage 5 target refinement  (12 months, Alpaca IEX)
#
# Stage 4 peak: VOL=1.0, ADX=20, SL=1.5, TP=10  →  5 trades, WR=60%, +14.65%
# Target: 20%+  →  need more trades OR higher TP at ≥50% WR
#
# Stage 5 strategy:
#   - Push TP higher (10-20x) to squeeze more from existing wins
#   - Vary ADX (18-22) and VOL (0.8-1.2) to find more trades w/o WR loss
#   - Vary PB_PCT (0.15-0.25) for tighter or wider pullback tolerance
#   - Also test EMA_SLOPE=1 back on (boosts WR but reduces trade count)
#
# Grid (648 combos):
#   EMA_SLOPE   : [0, 1]
#   VOL_MULT    : [0.8, 0.9, 1.0, 1.2]
#   ADX_THRESH  : [18, 20, 22]
#   PB_PCT      : [0.15, 0.20, 0.25]
#   TP_MULT     : [10, 11, 12, 14, 16, 20]
#   SL_MULT=1.5, RISK=[2%,2.5%,3%]  → but tuned in inner loop
#
# Fixed: RSI=(30,55), MIN_BODY=0.15, ATR_FLOOR=0.001, PANIC=1.5,
#        MOMENTUM_BARS=5, NO RSI_DIR filter, SL_MULT=1.5
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["alpaca-py", "pandas", "numpy", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import os
import pandas as pd
import numpy as np
import pytz
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

EMA_FAST   = 21;  EMA_MID = 50;  EMA_SLOW  = 200
ADX_LEN    = 14;  RSI_LEN = 14;  ATR_LEN   = 14
VOL_LEN    = 20;  ATR_BL_LEN = 60

MIN_BODY             = 0.15
ATR_FLOOR            = 0.0010
PANIC_MULT           = 1.5
SL_MULT              = 1.5
RSI_LO_S             = 30;  RSI_HI_S = 55
MOMENTUM_BARS        = 5
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
TP_COOLDOWN_BARS     = 2

# ── Sweep grid ────────────────────────────────────────────────────────────────
EMA_SLOPE_RANGE  = [0, 1]
VOL_MULT_RANGE   = [0.8, 0.9, 1.0, 1.2]
ADX_THRESH_RANGE = [18, 20, 22]
PB_PCT_RANGE     = [0.15, 0.20, 0.25]
TP_RANGE         = [10.0, 11.0, 12.0, 14.0, 16.0, 20.0]
RISK_RANGE       = [0.020, 0.025, 0.030]

total = (len(EMA_SLOPE_RANGE) * len(VOL_MULT_RANGE) * len(ADX_THRESH_RANGE)
         * len(PB_PCT_RANGE) * len(TP_RANGE) * len(RISK_RANGE))
print(f"Combinations: {total}")

# ── Download once ─────────────────────────────────────────────────────────────
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

raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample(
    "10min", label="left", closed="left", origin="start_day"
).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df = df[df["Volume"] > 0].dropna()
print(f"  10m bars: {len(df)}  |  {df.index[0]}..{df.index[-1]}")

# ── Indicators ─────────────────────────────────────────────────────────────────
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

up_m  = df["High"] - df["High"].shift(1)
dn_m  = df["Low"].shift(1) - df["Low"]
pdm   = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
ndm   = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
sp    = pd.Series(pdm, index=df.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
sn    = pd.Series(ndm, index=df.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * sp / df["ATR"]
df["DI_MINUS"] = 100 * sn / df["ATR"]
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
    (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1 / ADX_LEN, adjust=False).mean()
df.dropna(inplace=True)

# ── Stable booleans ────────────────────────────────────────────────────────────
body_size    = (df["Close"] - df["Open"]).abs() / df["ATR"]
is_panic     = df["ATR"] > df["ATR_BL"] * PANIC_MULT
atr_fl_ok    = df["ATR"] / df["Close"] >= ATR_FLOOR
momentum_s   = df["Close"] < df["Close"].shift(MOMENTUM_BARS)
ema_bear     = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
ema_sl_down  = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
rsi_ok       = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

adx_a      = df["ADX"].values
rsi_ok_a   = rsi_ok.values
vol_arr    = df["Volume"].values
vol_ma_arr = df["VOL_MA"].values
close_a    = df["Close"].values
high_a     = df["High"].values
low_a      = df["Low"].values
atr_a      = df["ATR"].values
ema_sl_a   = ema_sl_down.values

# base_static: indicators not swept (except vol, adx, pb, ema_slope)
base_static = (atr_fl_ok & ~is_panic & ema_bear & momentum_s & rsi_ok).values

print(f"\nRunning {total} combinations...")

results = []
done    = 0

for ema_slope in EMA_SLOPE_RANGE:
    for vol_mult in VOL_MULT_RANGE:
        vol_ok_a = (vol_arr >= vol_ma_arr * vol_mult)

        for pb_pct in PB_PCT_RANGE:
            tol_frac  = pb_pct / 100.0
            pb_tol_dn = df["EMA_FAST"].shift(1) * (1.0 - tol_frac)
            short_pb  = (
                (df["High"].shift(1) >= pb_tol_dn) &
                (df["Close"] < df["EMA_FAST"]) &
                (df["Close"] < df["Open"]) &
                (body_size >= MIN_BODY)
            ).values

            for adx_thresh in ADX_THRESH_RANGE:
                trending_a = adx_a > adx_thresh
                sig = base_static & short_pb & vol_ok_a & trending_a
                if ema_slope:
                    sig = sig & ema_sl_a

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

                        for i in range(len(close_a)):
                            cl = close_a[i]
                            hi = high_a[i]
                            lo = low_a[i]
                            av = atr_a[i]
                            sd = av * SL_MULT

                            if pos is not None:
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
                                        wins += 1
                                        gross_p += dp
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

                            if pos is None and sd > 0:
                                if cooldown > 0:
                                    cooldown -= 1
                                elif sig[i]:
                                    notl = min(equity * risk_pct / sd * cl, equity * 5.0)
                                    pos  = {
                                        "entry":    cl,
                                        "sl":       cl + sd,
                                        "tp":       cl - av * tp_mult,
                                        "best":     cl,
                                        "notional": notl,
                                    }

                        ret    = (equity / INITIAL_CAPITAL - 1) * 100
                        wr     = wins / n_trades * 100 if n_trades else 0.0
                        pf     = (gross_p / abs(gross_l)) if gross_l < 0 else (float("inf") if gross_p > 0 else 0.0)
                        mdd    = (min_eq / INITIAL_CAPITAL - 1) * 100
                        calmar = ret / abs(mdd) if mdd != 0 else float("inf")

                        results.append({
                            "ema_slope":  ema_slope,
                            "vol_mult":   vol_mult,
                            "pb_pct":     pb_pct,
                            "adx_thresh": adx_thresh,
                            "tp":         tp_mult,
                            "risk":       risk_pct,
                            "n":          n_trades,
                            "wr":         round(wr, 1),
                            "pf":         round(pf, 3),
                            "ret":        round(ret, 2),
                            "mdd":        round(mdd, 2),
                            "calmar":     round(calmar, 2),
                        })
                        done += 1
                        if done % 150 == 0:
                            best = max(r["ret"] for r in results)
                            print(f"  {done}/{total}  best so far: {best:+.2f}%")

rdf = pd.DataFrame(results).sort_values("ret", ascending=False)
out = "sweep_apm_v4_30m_s5.csv"
rdf.to_csv(out, index=False)
print(f"\nSweep done → {out}")

print(f"\nTop 30 by net return (all trade counts):")
print(rdf.head(30).to_string(index=False))

print(f"\nTop 20 by net return (min 5 trades):")
top5 = rdf[rdf["n"] >= 5].head(20)
print(top5.to_string(index=False))

print(f"\nConfigs with ret>20%:")
top20 = rdf[rdf["ret"] > 20]
print(top20.to_string(index=False) if not top20.empty else "  (none found)")
