# ─────────────────────────────────────────────────────────────────────────────
# APM v4 — CLM 30m — Stage 2 parameter sweep  (12 months, Alpaca IEX)
#
# Stage 1 finding: strict v4 filter stack (EMA slope + RSI direction +
# DI spread + ADX slope) caps signal count at 8-12 trades, WR ≤ 37.5%,
# net return ≤ +1.02%.  Need to relax individual filters to unlock quality.
#
# Stage 2 grid (576 combos):
#   RSI_DIR_FILTER  : [0=off, 1=on]      ← v4-specific, possibly too strict
#   EMA_SLOPE_FILTER: [0=off, 1=on]      ← v4-specific, possibly too strict
#   PB_PCT          : [0.20, 0.30, 0.40, 0.50]
#   ADX_THRESH      : [14, 17, 20]
#   TP_MULT         : [6.0, 7.0, 8.0, 9.0]
#   RISK_PCT        : [2.0%, 2.5%, 3.0%]
#
# Fixed: SL=2.0, VOL_MULT=0.50, MIN_BODY=0.15, ATR_FLOOR=0.001,
#        PANIC=1.5, DI_SPREAD=0, MOMENTUM_BARS=5, CONSEC_LOSS_CD on
#        ADX_SLOPE=off (stage 1: no benefit), SHORTS_ONLY
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

VOL_MULT             = 0.50
MIN_BODY             = 0.15
ATR_FLOOR            = 0.0010
PANIC_MULT           = 1.5
SL_MULT              = 2.0
TRAIL_ACT            = 99.0   # effectively disabled
TRAIL_DIST           = 1.5
RSI_LO_S             = 30
RSI_HI_S             = 62
MOMENTUM_BARS        = 5
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
TP_COOLDOWN_BARS     = 2

# ── Sweep grid ────────────────────────────────────────────────────────────────
RSI_DIR_RANGE    = [0, 1]           # 0=off  1=on
EMA_SLOPE_RANGE  = [0, 1]           # 0=off  1=on
PB_PCT_RANGE     = [0.20, 0.30, 0.40, 0.50]
ADX_THRESH_RANGE = [14, 17, 20]
TP_RANGE         = [6.0, 7.0, 8.0, 9.0]
RISK_RANGE       = [0.020, 0.025, 0.030]

total = (len(RSI_DIR_RANGE) * len(EMA_SLOPE_RANGE) * len(PB_PCT_RANGE)
         * len(ADX_THRESH_RANGE) * len(TP_RANGE) * len(RISK_RANGE))
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

# ── Resample 5m → 30m ─────────────────────────────────────────────────────────
raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample(
    "30min", label="left", closed="left", origin="start_day"
).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df = df[df["Volume"] > 0].dropna()
print(f"  30m bars: {len(df)}  |  {df.index[0]}..{df.index[-1]}")

# ── Pre-compute indicators (fixed across sweep) ───────────────────────────────
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

# ── Pre-compute stable boolean series ─────────────────────────────────────────
body_size      = (df["Close"] - df["Open"]).abs() / df["ATR"]
is_panic       = df["ATR"] > df["ATR_BL"] * PANIC_MULT
ema_bear       = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)   # v4 EMA slope filter
rsi_falling    = df["RSI"] < df["RSI"].shift(1)              # v4 RSI direction filter
rsi_short_ok   = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
vol_ok         = df["Volume"] >= df["VOL_MA"] * VOL_MULT
atr_floor_ok   = df["ATR"] / df["Close"] >= ATR_FLOOR
momentum_ok    = df["Close"] < df["Close"].shift(MOMENTUM_BARS)

# Constant short-pullback base (body, EMA stack, vol, atr floor, panic, momentum)
# PB_PCT is swept, so short_pb is computed inside the loop
base_const = ema_bear & vol_ok & atr_floor_ok & momentum_ok & ~is_panic

# Arrays for fast inner loop
bar_arr  = df.index.tolist()
close_a  = df["Close"].values
high_a   = df["High"].values
low_a    = df["Low"].values
atr_a    = df["ATR"].values
adx_a    = df["ADX"].values
ema_f_a  = df["EMA_FAST"].values
body_a   = body_size.values

rsi_fall_a  = rsi_falling.values
rsi_sok_a   = rsi_short_ok.values
ema_sl_a    = ema_slope_down.values
base_c_a    = base_const.values
ema_hi1_a   = df["EMA_FAST"].shift(1).values   # EMA_FAST[1]
high1_a     = df["High"].shift(1).values        # High[1]

print(f"\nRunning {total} combinations...")

results = []
done    = 0

for rsi_dir in RSI_DIR_RANGE:
    for ema_slope in EMA_SLOPE_RANGE:
        for pb_pct in PB_PCT_RANGE:
            tol_frac = pb_pct / 100.0
            # pullback condition depends on pb_pct
            pb_tol_dn = df["EMA_FAST"].shift(1) * (1.0 - tol_frac)
            short_pb  = (
                (df["High"].shift(1) >= pb_tol_dn) &
                (df["Close"] < df["EMA_FAST"])      &
                (df["Close"] < df["Open"])           &
                (body_size >= MIN_BODY)
            )
            short_pb_a = short_pb.values

            for adx_thresh in ADX_THRESH_RANGE:
                is_trending_a = (adx_a > adx_thresh)

                # Build per-combo signal array (without risk/tp params)
                sig = np.ones(len(df), dtype=bool)
                sig &= base_c_a
                sig &= short_pb_a
                sig &= is_trending_a
                if rsi_dir:
                    sig &= rsi_fall_a
                sig &= rsi_sok_a
                if ema_slope:
                    sig &= ema_sl_a

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

                        for i in range(len(bar_arr)):
                            cl = close_a[i]
                            hi = high_a[i]
                            lo = low_a[i]
                            av = atr_a[i]
                            sd = av * SL_MULT

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
                            "rsi_dir":    rsi_dir,
                            "ema_slope":  ema_slope,
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
                        if done % 100 == 0:
                            best = max(r["ret"] for r in results)
                            print(f"  {done}/{total}  best so far: {best:+.2f}%")

rdf = pd.DataFrame(results).sort_values("ret", ascending=False)
out = "sweep_apm_v4_30m_s2.csv"
rdf.to_csv(out, index=False)
print(f"\nSweep done → {out}")

print(f"\nTop 20 by net return (min 6 trades):")
top = rdf[rdf["n"] >= 6].head(20)
print(top.to_string(index=False))

print(f"\nTop 20 by Calmar (min 6 trades, ret>5%):")
top_c = rdf[(rdf["n"] >= 6) & (rdf["ret"] > 5)].sort_values("calmar", ascending=False).head(20)
print(top_c.to_string(index=False))
