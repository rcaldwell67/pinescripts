# ─────────────────────────────────────────────────────────────────────────────
# APM v4 — CLM 10m — Stage 4 parameter sweep  (12 months, Alpaca IEX)
#
# Stage 3 finding (15m): max +11.79%, WR=30.4% — WR is the bottleneck.
# v2 achieves WR=75% at 10m with VOL_MULT=0.7 and tighter RSI range.
#
# Stage 4 key changes:
#   - Resample 5m → 10m  (same TF as v2 best config)
#   - Sweep VOL_MULT  [0.5, 0.7, 1.0]  ← higher = better WR
#   - Sweep RSI_LO_S/RSI_HI_S  [30/55, 28/58, 32/52]  ← tighter = better WR
#   - No RSI direction / no EMA slope  (v2 doesn't use these)
#   - Sweep ADX [14, 17, 20], TP [7,8,9,10], RISK [2%,2.5%], SL [1.5,2.0]
#
# Grid (3×3×3×4×2×2 = 432 combos):
#   VOL_MULT    : [0.5, 0.7, 1.0]
#   RSI_BAND    : [(30,55), (28,58), (32,52)]
#   ADX_THRESH  : [14, 17, 20]
#   TP_MULT     : [7.0, 8.0, 9.0, 10.0]
#   RISK_PCT    : [2.0%, 2.5%]
#   SL_MULT     : [1.5, 2.0]
#
# Fixed: PB_PCT=0.20, MIN_BODY=0.15, ATR_FLOOR=0.001, PANIC=1.5,
#        MOMENTUM_BARS=5, CONSEC_LOSS_CD on, SHORTS_ONLY
#        No RSI direction filter, No EMA slope filter
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

# Fixed params
EMA_FAST   = 21;  EMA_MID   = 50;  EMA_SLOW  = 200
ADX_LEN    = 14;  RSI_LEN   = 14;  ATR_LEN   = 14
VOL_LEN    = 20;  ATR_BL_LEN = 60

PB_PCT               = 0.20
MIN_BODY             = 0.15
ATR_FLOOR            = 0.0010
PANIC_MULT           = 1.5
TRAIL_ACT            = 99.0
MOMENTUM_BARS        = 5
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
TP_COOLDOWN_BARS     = 2

# ── Sweep grid ────────────────────────────────────────────────────────────────
VOL_MULT_RANGE   = [0.5, 0.7, 1.0]
RSI_BAND_RANGE   = [(30, 55), (28, 58), (32, 52)]   # (lo, hi) for shorts
ADX_THRESH_RANGE = [14, 17, 20]
TP_RANGE         = [7.0, 8.0, 9.0, 10.0]
RISK_RANGE       = [0.020, 0.025]
SL_RANGE         = [1.5, 2.0]

total = (len(VOL_MULT_RANGE) * len(RSI_BAND_RANGE) * len(ADX_THRESH_RANGE)
         * len(TP_RANGE) * len(RISK_RANGE) * len(SL_RANGE))
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

# ── Resample 5m → 10m ─────────────────────────────────────────────────────────
raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample(
    "10min", label="left", closed="left", origin="start_day"
).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df = df[df["Volume"] > 0].dropna()
print(f"  10m bars: {len(df)}  |  {df.index[0]}..{df.index[-1]}")

# ── Pre-compute indicators ─────────────────────────────────────────────────────
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

# ── Pre-compute stable booleans ────────────────────────────────────────────────
tol_frac   = PB_PCT / 100.0
body_size  = (df["Close"] - df["Open"]).abs() / df["ATR"]
is_panic   = df["ATR"] > df["ATR_BL"] * PANIC_MULT
atr_fl_ok  = df["ATR"] / df["Close"] >= ATR_FLOOR
momentum_s = df["Close"] < df["Close"].shift(MOMENTUM_BARS)
ema_bear   = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - tol_frac)
short_pb   = (
    (df["High"].shift(1) >= pb_tol_dn) &
    (df["Close"] < df["EMA_FAST"]) &
    (df["Close"] < df["Open"]) &
    (body_size >= MIN_BODY)
)

# constant across vol/rsi/adx sweeps:
base_const = atr_fl_ok & ~is_panic & ema_bear & momentum_s & short_pb

adx_arr    = df["ADX"].values
rsi_arr    = df["RSI"].values
vol_arr    = df["Volume"].values
vol_ma_arr = df["VOL_MA"].values
close_a    = df["Close"].values
high_a     = df["High"].values
low_a      = df["Low"].values
atr_a      = df["ATR"].values
base_a     = base_const.values

print(f"\nRunning {total} combinations...")

results = []
done    = 0

for vol_mult in VOL_MULT_RANGE:
    vol_ok_a = (vol_arr >= vol_ma_arr * vol_mult)

    for (rsi_lo, rsi_hi) in RSI_BAND_RANGE:
        rsi_ok_a = (rsi_arr >= rsi_lo) & (rsi_arr <= rsi_hi)

        for adx_thresh in ADX_THRESH_RANGE:
            trending_a = adx_arr > adx_thresh
            sig = base_a & vol_ok_a & rsi_ok_a & trending_a

            for sl_mult in SL_RANGE:
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
                            sd = av * sl_mult

                            htp = hsl = False
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

                            if pos is None:
                                if cooldown > 0:
                                    cooldown -= 1
                                elif sig[i] and sd > 0:
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
                            "vol_mult":   vol_mult,
                            "rsi_lo":     rsi_lo,
                            "rsi_hi":     rsi_hi,
                            "adx_thresh": adx_thresh,
                            "sl":         sl_mult,
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
                        if done % 100 == 0:
                            best = max(r["ret"] for r in results)
                            print(f"  {done}/{total}  best so far: {best:+.2f}%")

rdf = pd.DataFrame(results).sort_values("ret", ascending=False)
out = "sweep_apm_v4_30m_s4.csv"
rdf.to_csv(out, index=False)
print(f"\nSweep done → {out}")

print(f"\nTop 25 by net return (min 6 trades):")
top = rdf[rdf["n"] >= 6].head(25)
print(top.to_string(index=False))

print(f"\nTop 20 by Calmar (min 6 trades, ret>10%):")
top_c = rdf[(rdf["n"] >= 6) & (rdf["ret"] > 10)].sort_values("calmar", ascending=False).head(20)
print(top_c.to_string(index=False))

print(f"\nConfigs with ret>20% (min 4 trades):")
top20 = rdf[(rdf["ret"] > 20) & (rdf["n"] >= 4)]
print(top20.to_string(index=False) if not top20.empty else "  (none found)")
