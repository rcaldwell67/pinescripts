# ─────────────────────────────────────────────────────────────────────────────
# APM v4 — CLM 15m — Stage 3 parameter sweep  (12 months, Alpaca IEX)
#
# Stage 2 finding (30m): max +7.61%, only 9 trades at WR=33.3%.
# CLM 30m is too coarse — not enough quality signals to hit 20%.
#
# Stage 3 changes:
#   - Resample 5m → 15m  (2× more bars vs 30m → more signals)
#   - Add LONGS option  (CLM can trend both ways)
#   - Sweep SL_MULT [1.5, 2.0]  (tighter SL → more qty → more impact per trade)
#   - Keep best stage-2 structural params: RSI_DIR=1, EMA_SLOPE=1, PB=0.20
#     but also test RSI off and EMA_SLOPE off for longs
#
# Grid (1152 combos):
#   RSI_DIR_FILTER  : [0=off, 1=on]
#   EMA_SLOPE_FILTER: [0=off, 1=on]
#   TRADE_MODE      : [0=shorts, 1=longs, 2=both]
#   ADX_THRESH      : [14, 17, 20]
#   SL_MULT         : [1.5, 2.0]
#   TP_MULT         : [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
#   RISK_PCT        : [2.0%, 2.5%]
#
# Fixed: PB_PCT=0.20, VOL_MULT=0.50, MIN_BODY=0.15, ATR_FLOOR=0.001,
#        PANIC=1.5, MOMENTUM_BARS=5, CONSEC_LOSS_CD on
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
VOL_MULT             = 0.50
MIN_BODY             = 0.15
ATR_FLOOR            = 0.0010
PANIC_MULT           = 1.5
TRAIL_ACT            = 99.0
TRAIL_DIST           = 1.5
RSI_LO_S             = 30;  RSI_HI_S = 62
RSI_LO_L             = 38;  RSI_HI_L = 68
MOMENTUM_BARS        = 5
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
TP_COOLDOWN_BARS     = 2

# ── Sweep grid ────────────────────────────────────────────────────────────────
RSI_DIR_RANGE    = [0, 1]
EMA_SLOPE_RANGE  = [0, 1]
TRADE_MODE_RANGE = [0, 1, 2]          # 0=shorts  1=longs  2=both
ADX_THRESH_RANGE = [14, 17, 20]
SL_RANGE         = [1.5, 2.0]
TP_RANGE         = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
RISK_RANGE       = [0.020, 0.025]

total = (len(RSI_DIR_RANGE) * len(EMA_SLOPE_RANGE) * len(TRADE_MODE_RANGE)
         * len(ADX_THRESH_RANGE) * len(SL_RANGE) * len(TP_RANGE) * len(RISK_RANGE))
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

# ── Resample 5m → 15m ─────────────────────────────────────────────────────────
raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample(
    "15min", label="left", closed="left", origin="start_day"
).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df = df[df["Volume"] > 0].dropna()
print(f"  15m bars: {len(df)}  |  {df.index[0]}..{df.index[-1]}")

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

# ── Pre-compute stable boolean series ─────────────────────────────────────────
tol_frac   = PB_PCT / 100.0
body_size  = (df["Close"] - df["Open"]).abs() / df["ATR"]
is_panic   = df["ATR"] > df["ATR_BL"] * PANIC_MULT
atr_fl_ok  = df["ATR"] / df["Close"] >= ATR_FLOOR
vol_ok     = df["Volume"] >= df["VOL_MA"] * VOL_MULT
momentum_s = df["Close"] < df["Close"].shift(MOMENTUM_BARS)
momentum_l = df["Close"] > df["Close"].shift(MOMENTUM_BARS)

ema_bear = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
ema_bull = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)

rsi_falling   = df["RSI"] < df["RSI"].shift(1)
rsi_rising    = df["RSI"] > df["RSI"].shift(1)
rsi_s_ok      = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
rsi_l_ok      = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)

pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - tol_frac)
pb_tol_up  = df["EMA_FAST"].shift(1) * (1.0 + tol_frac)
short_pb_base = (
    (df["High"].shift(1) >= pb_tol_dn) &
    (df["Close"] < df["EMA_FAST"]) &
    (df["Close"] < df["Open"]) &
    (body_size >= MIN_BODY)
)
long_pb_base = (
    (df["Low"].shift(1) <= pb_tol_up) &
    (df["Close"] > df["EMA_FAST"]) &
    (df["Close"] > df["Open"]) &
    (body_size >= MIN_BODY)
)

base_common = vol_ok & atr_fl_ok & ~is_panic
short_base  = base_common & short_pb_base & ema_bear & rsi_s_ok & momentum_s
long_base   = base_common & long_pb_base  & ema_bull & rsi_l_ok & momentum_l

# Arrays for fast inner loop
close_a   = df["Close"].values
high_a    = df["High"].values
low_a     = df["Low"].values
atr_a     = df["ATR"].values
adx_a     = df["ADX"].values
r_fall_a  = rsi_falling.values
r_rise_a  = rsi_rising.values
es_dn_a   = ema_slope_down.values
es_up_a   = ema_slope_up.values
s_base_a  = short_base.values
l_base_a  = long_base.values

print(f"\nRunning {total} combinations...")

results = []
done    = 0

for rsi_dir in RSI_DIR_RANGE:
    for ema_slope in EMA_SLOPE_RANGE:
        # Build short/long signal arrays for this filter combo
        s_sig = s_base_a.copy()
        l_sig = l_base_a.copy()
        if rsi_dir:
            s_sig &= r_fall_a
            l_sig &= r_rise_a
        if ema_slope:
            s_sig &= es_dn_a
            l_sig &= es_up_a

        for trade_mode in TRADE_MODE_RANGE:
            do_short = trade_mode in (0, 2)
            do_long  = trade_mode in (1, 2)

            for adx_thresh in ADX_THRESH_RANGE:
                trending_a = adx_a > adx_thresh
                ss = s_sig & trending_a if do_short else np.zeros(len(df), dtype=bool)
                ls = l_sig & trending_a if do_long  else np.zeros(len(df), dtype=bool)

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
                                    d = pos["dir"]
                                    if d == "short":
                                        if lo < pos["best"]:
                                            pos["best"] = lo
                                        htp = lo <= pos["tp"]
                                        hsl = hi >= pos["sl"]
                                    else:
                                        if hi > pos["best"]:
                                            pos["best"] = hi
                                        htp = hi >= pos["tp"]
                                        hsl = lo <= pos["sl"]

                                if htp or hsl:
                                    xp = pos["tp"] if htp else pos["sl"]
                                    d  = pos["dir"]
                                    pnl = ((pos["entry"] - xp) / pos["entry"] if d == "short"
                                           else (xp - pos["entry"]) / pos["entry"])
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

                                if pos is None and cooldown == 0 and sd > 0:
                                    if ss[i]:
                                        notl = min(equity * risk_pct / sd * cl, equity * 5.0)
                                        pos  = {
                                            "dir":      "short",
                                            "entry":    cl,
                                            "sl":       cl + sd,
                                            "tp":       cl - av * tp_mult,
                                            "best":     cl,
                                            "notional": notl,
                                        }
                                    elif ls[i]:
                                        notl = min(equity * risk_pct / sd * cl, equity * 5.0)
                                        pos  = {
                                            "dir":      "long",
                                            "entry":    cl,
                                            "sl":       cl - sd,
                                            "tp":       cl + av * tp_mult,
                                            "best":     cl,
                                            "notional": notl,
                                        }
                                elif cooldown > 0 and pos is None:
                                    cooldown -= 1

                            ret    = (equity / INITIAL_CAPITAL - 1) * 100
                            wr     = wins / n_trades * 100 if n_trades else 0.0
                            pf     = (gross_p / abs(gross_l)) if gross_l < 0 else (float("inf") if gross_p > 0 else 0.0)
                            mdd    = (min_eq / INITIAL_CAPITAL - 1) * 100
                            calmar = ret / abs(mdd) if mdd != 0 else float("inf")

                            tm_str = {0: "shorts", 1: "longs", 2: "both"}[trade_mode]
                            results.append({
                                "rsi_dir":    rsi_dir,
                                "ema_slope":  ema_slope,
                                "trade_mode": tm_str,
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
                            if done % 150 == 0:
                                best = max(r["ret"] for r in results)
                                print(f"  {done}/{total}  best so far: {best:+.2f}%")

rdf = pd.DataFrame(results).sort_values("ret", ascending=False)
out = "sweep_apm_v4_30m_s3.csv"
rdf.to_csv(out, index=False)
print(f"\nSweep done → {out}")

print(f"\nTop 25 by net return (min 8 trades):")
top = rdf[rdf["n"] >= 8].head(25)
print(top.to_string(index=False))

print(f"\nTop 20 by Calmar (min 8 trades, ret>10%):")
top_c = rdf[(rdf["n"] >= 8) & (rdf["ret"] > 10)].sort_values("calmar", ascending=False).head(20)
print(top_c.to_string(index=False))

print(f"\nConfigs with ret>20% (any trade count):")
top20 = rdf[rdf["ret"] > 20]
print(top20.to_string(index=False) if not top20.empty else "  (none found)")
