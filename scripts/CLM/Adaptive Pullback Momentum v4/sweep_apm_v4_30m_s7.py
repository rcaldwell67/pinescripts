# ─────────────────────────────────────────────────────────────────────────────
# APM v4 — CLM 30m — Stage 7 trail parameter sweep  (12 months, Alpaca IEX)
#
# Stage 6 ceiling: +10.99%  (both, adx=10, pb=0.5, vol=1.2, sl=1.5,
#                             tp=8, risk=2.5%, rsi_dir=1, ema_slope=1)
#
# Root cause: TRAIL_ACT=2.5×ATR is too large for 30m bars — trail never
# activates so exits are pure SL (many small losses drag returns).
#
# Stage 7 strategy: shrink TRAIL_ACT so trail kicks in sooner on winning
# trades, and tighten TRAIL_DIST to lock in more profit. Also push TP high
# (32-999×) so it's effectively "unlimited" and trail does all exit work.
#
# Grid (1,728 combos):
#   trail_act  : [0.5, 1.0, 1.5, 2.5]          ← key variable
#   trail_dist : [0.3, 0.5, 0.8, 1.5]          ← key variable
#   tp_mult    : [8, 16, 32, 999]               ← effectively unlimited
#   adx_thresh : [10, 14, 18]
#   sl_mult    : [1.5, 2.0]
#   risk_pct   : [0.020, 0.025, 0.030]
#
# Fixed (from best S6): ema_slope=1, rsi_dir=1, trade_mode=both, pb=0.5%,
#   vol=1.2, MIN_BODY=0.15, PANIC=1.5, RSI bounds unchanged
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["alpaca-py", "pandas", "numpy", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import os, itertools, csv
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

EMA_FAST   = 21;  EMA_MID   = 50;  EMA_SLOW  = 200
ADX_LEN    = 14;  RSI_LEN   = 14;  ATR_LEN   = 14
VOL_LEN    = 20;  ATR_BL_LEN = 60

# Fixed params (best S6 config)
MIN_BODY   = 0.15
ATR_FLOOR  = 0.001
PANIC_MULT = 1.5
PB_PCT     = 0.50
VOL_MULT   = 1.2
RSI_DIR    = True
EMA_SLOPE  = True
RSI_LO_S   = 30;  RSI_HI_S = 62
RSI_LO_L   = 38;  RSI_HI_L = 68
TRADE_LONGS = True;  TRADE_SHORTS = True

# ── Sweep grid ────────────────────────────────────────────────────────────────
GRID = {
    "trail_act":  [0.5, 1.0, 1.5, 2.5],
    "trail_dist": [0.3, 0.5, 0.8, 1.5],
    "tp_mult":    [8.0, 16.0, 32.0, 999.0],
    "adx_thresh": [10, 14, 18],
    "sl_mult":    [1.5, 2.0],
    "risk_pct":   [0.020, 0.025, 0.030],
}

keys   = list(GRID.keys())
combos = list(itertools.product(*[GRID[k] for k in keys]))
print(f"Combinations: {len(combos)}")

# ── Download 5m data ──────────────────────────────────────────────────────────
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
print(f"  raw 5m bars: {len(raw)}")

# ── Resample 5m → 30m ─────────────────────────────────────────────────────────
raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample(
    "30min", label="left", closed="left", origin="start_day"
).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df = df[df["Volume"] > 0].dropna()
print(f"  30m bars: {len(df)}  |  {df.index[0]}..{df.index[-1]}")

# ── Compute indicators ────────────────────────────────────────────────────────
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta  = df["Close"].diff()
avg_g  = delta.clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
avg_l  = (-delta).clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - 100 / (1 + avg_g / avg_l.replace(0, 1e-10))

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
print(f"  bars after warmup: {len(df)}")

# ── Static signal masks (fixed params) ───────────────────────────────────────
tol       = PB_PCT / 100.0
body_size = (df["Close"] - df["Open"]).abs() / df["ATR"]
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT
atr_fl_ok   = df["ATR"] / df["Close"] >= ATR_FLOOR
body_ok     = body_size >= MIN_BODY

ema_bull = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_bear = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)

rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)
rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

pb_tol_up = df["EMA_FAST"].shift(1) * (1.0 + tol)
pb_tol_dn = df["EMA_FAST"].shift(1) * (1.0 - tol)

long_pb  = ((df["Low"].shift(1) <= pb_tol_up) & (df["Close"] > df["EMA_FAST"]) &
            (df["Close"] > df["Open"]) & body_ok)
short_pb = ((df["High"].shift(1) >= pb_tol_dn) & (df["Close"] < df["EMA_FAST"]) &
            (df["Close"] < df["Open"]) & body_ok)
vol_ok = df["Volume"] >= df["VOL_MA"] * VOL_MULT

# Pre-build fixed long/short signal base (adx swept below)
_long_base  = (long_pb  & ema_bull  & ema_slope_up   & rsi_rising  &
               rsi_long_ok  & vol_ok & atr_fl_ok & ~is_panic)
_short_base = (short_pb & ema_bear  & ema_slope_down  & rsi_falling &
               rsi_short_ok & vol_ok & atr_fl_ok & ~is_panic)

# ── Simulation function ───────────────────────────────────────────────────────
def run(trail_act, trail_dist, tp_mult, adx_thresh, sl_mult, risk_pct):
    is_trending = df["ADX"] > adx_thresh
    long_sig  = _long_base  & is_trending
    short_sig = _short_base & is_trending

    equity = INITIAL_CAPITAL
    pos    = None
    trades = []
    eqcurve= []

    for ts, row in df.iterrows():
        close = float(row["Close"]); high = float(row["High"])
        low   = float(row["Low"]);   atr  = float(row["ATR"])
        sd    = atr * sl_mult

        htp = hsl = False
        if pos is not None:
            d = pos["direction"]
            if d == "long":
                if high > pos["best"]: pos["best"] = high
                if pos["best"] >= pos["trail_activate_px"]:
                    pos["sl"] = max(pos["sl"], pos["best"] - pos["trail_dist"])
                htp = high >= pos["tp"]
                hsl = low  <= pos["sl"]
            else:
                if low < pos["best"]: pos["best"] = low
                if pos["best"] <= pos["trail_activate_px"]:
                    pos["sl"] = min(pos["sl"], pos["best"] + pos["trail_dist"])
                htp = low  <= pos["tp"]
                hsl = high >= pos["sl"]

        if htp or hsl:
            d  = pos["direction"]
            xp = pos["tp"] if htp else pos["sl"]
            pnl = ((xp - pos["entry"]) / pos["entry"] if d == "long"
                   else (pos["entry"] - xp) / pos["entry"])
            dp = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
            equity += dp
            trades.append(dp)
            pos = None

        if pos is None:
            sig = ("long"  if bool(long_sig[ts])  else
                   "short" if bool(short_sig[ts]) else None)
            if sig:
                sl  = close - sd if sig == "long" else close + sd
                tp  = (close + atr * tp_mult if sig == "long"
                       else close - atr * tp_mult)
                tap = (close + atr * trail_act if sig == "long"
                       else close - atr * trail_act)
                stop_dist = abs(close - sl)
                notl = min(equity * risk_pct / stop_dist * close, equity * 5.0)
                pos = {
                    "direction": sig,
                    "entry": close,
                    "sl": sl, "tp": tp,
                    "best": close,
                    "notional": notl,
                    "trail_activate_px": tap,
                    "trail_dist": atr * trail_dist,
                }

        eqcurve.append(equity)

    if not trades:
        return None
    n    = len(trades)
    wins = [t for t in trades if t > 0]
    loss = [t for t in trades if t <= 0]
    wr   = len(wins) / n * 100
    pf   = sum(wins) / abs(sum(loss)) if loss else float("inf")
    ret  = (equity / INITIAL_CAPITAL - 1) * 100
    eq_s = pd.Series(eqcurve)
    mdd  = ((eq_s - eq_s.cummax()) / eq_s.cummax() * 100).min()
    calmar = ret / abs(mdd) if mdd != 0 else float("inf")
    return n, round(wr, 1), round(pf, 3), round(ret, 2), round(mdd, 2), round(calmar, 2)

# ── Run sweep ─────────────────────────────────────────────────────────────────
out_csv = "sweep_apm_v4_30m_s7.csv"
fieldnames = keys + ["n", "wr", "pf", "ret", "mdd", "calmar"]
best_ret = -999.0

with open(out_csv, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()

    for i, vals in enumerate(combos, 1):
        params = dict(zip(keys, vals))
        result = run(**params)
        if result is None:
            continue
        n, wr, pf, ret, mdd, calmar = result
        row = {**params, "n": n, "wr": wr, "pf": pf, "ret": ret,
               "mdd": mdd, "calmar": calmar}
        w.writerow(row)
        f.flush()

        if ret > best_ret:
            best_ret = ret
            print(f"  [{i}/{len(combos)}] NEW BEST: ret={ret:+.2f}%  "
                  f"n={n}  WR={wr}%  PF={pf}  MDD={mdd}%  Calmar={calmar}  — {params}")

print(f"\nSweep complete. Results → {out_csv}")
print(f"Best return found: {best_ret:+.2f}%")

# ── Top 10 ────────────────────────────────────────────────────────────────────
df_res = pd.read_csv(out_csv)
print("\nTop 10 by return (n >= 5):")
top = df_res[df_res["n"] >= 5].nlargest(10, "ret")
print(top.to_string(index=False))
