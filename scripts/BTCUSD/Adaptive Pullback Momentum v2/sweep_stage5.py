"""Stage-5 sweep for APM v2 BTCUSD 10m — intermediate signal parameter search

Goal: Find params with net_pct > 20% AND WR >= 80% on the 1-year Alpaca window.

Stage-4 found the gap:
  - Quality (ADX=20, pb=0.30): ~10 trades, WR=80% best gives +19.80%
  - Relaxed (ADX=15, pb=0.40): ~23 trades, WR=65%
  - Need the middle: ~15-18 trades, WR≥80%

Stage-5 approach: sweep signal params in the intermediate range
  ADX    : 16, 17, 18, 19, 20
  PB     : 0.28, 0.30, 0.33, 0.36, 0.40
  vol    : 0.5, 0.6, 0.7
  min_body: 0.15, 0.20

Exit dimensions (focused on quality-oriented range):
  tp_mult    : 7.0, 8.0, 9.0
  risk_pct   : 1.5, 2.0, 2.5
  trail_dist : 0.2, 0.3, 0.4
  max_bars   : 20, 25, 30

Fixed: sl=2.0, trail_act=3.5, session 9-14, panic=1.5, atr_floor=0.001

Total: 5×5×3×2 signal × 3×3×3×3 exit = 150 × 81 = 12,150 combos
"""

import subprocess, sys
for pkg in ["alpaca-py", "pandas", "numpy"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import pandas as pd
import numpy as np
import pytz, itertools
from datetime import datetime, timezone
from pathlib import Path
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

_ET = pytz.timezone("America/New_York")

# ─── Alpaca credentials ───────────────────────────────────────────────────────
ALPACA_KEY    = "PKNIYXYVLHKHF43IIEUQIA42DJ"
ALPACA_SECRET = "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u"

TICKER         = "BTC/USD"
BACKTEST_END   = datetime(2026, 3, 14, tzinfo=timezone.utc)
BACKTEST_START = datetime(2025, 3, 14, tzinfo=timezone.utc)

# ─── Fixed indicator params ───────────────────────────────────────────────────
EMA_FAST         = 21;  EMA_MID  = 50;  EMA_SLOW = 200
ADX_LEN          = 14;  RSI_LEN  = 14;  ATR_LEN  = 14;  VOL_LEN = 20
ATR_BL_LEN       = 60
PANIC_MULT       = 1.5
ATR_FLOOR        = 0.001
RSI_LO_S         = 32.0;  RSI_HI_S = 58.0
SESSION_START_ET = 9;     SESSION_END_ET = 14
MOMENTUM_BARS    = 5
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
COMMISSION_PCT   = 0.0006
INITIAL_CAPITAL  = 10_000.0
SL_MULT          = 2.0
TRAIL_ACT        = 3.5

# ─── Sweep grids ─────────────────────────────────────────────────────────────
ADX_VALS      = [16, 17, 18, 19, 20]
PB_VALS       = [0.28, 0.30, 0.33, 0.36, 0.40]
VOL_VALS      = [0.5, 0.6, 0.7]
MIN_BODY_VALS = [0.15, 0.20]

TP_VALS        = [7.0, 8.0, 9.0]
RISK_VALS      = [1.5, 2.0, 2.5]
TRAIL_DIST_VALS= [0.2, 0.3, 0.4]
MAX_BARS_VALS  = [20, 25, 30]

total = (len(ADX_VALS) * len(PB_VALS) * len(VOL_VALS) * len(MIN_BODY_VALS) *
         len(TP_VALS) * len(RISK_VALS) * len(TRAIL_DIST_VALS) * len(MAX_BARS_VALS))
print(f"Stage-5 sweep: {total:,} combos")

# ─── Fetch + resample ─────────────────────────────────────────────────────────
print(f"\nFetching {TICKER} 5m ({BACKTEST_START.date()} → {BACKTEST_END.date()}) ...")
client = CryptoHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
TF5  = TimeFrame(5, TimeFrameUnit.Minute)
req  = CryptoBarsRequest(
    symbol_or_symbols=TICKER, timeframe=TF5,
    start=BACKTEST_START, end=BACKTEST_END,
)
bars = client.get_crypto_bars(req)
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

raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df10 = raw_et.resample(
    "10min", label="left", closed="left", origin="start_day"
).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df10 = df10[df10["Volume"] > 0].dropna()
print(f"  10m bars: {len(df10)}  |  {df10.index[0]}..{df10.index[-1]}")

# ─── Pre-compute price-independent indicators (fixed params) ─────────────────
df = df10.copy()
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta  = df["Close"].diff()
avg_g  = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l  = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up_move  = df["High"] - df["High"].shift(1)
dn_move  = df["Low"].shift(1) - df["Low"]
plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
s_plus   = pd.Series(plus_dm,  index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
s_minus  = pd.Series(minus_dm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * s_plus  / df["ATR"].replace(0, 1e-10)
df["DI_MINUS"] = 100 * s_minus / df["ATR"].replace(0, 1e-10)
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
    (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()

df.dropna(inplace=True)
df["ET_HOUR"] = df.index.hour
print(f"  usable bars after warmup: {len(df)}")

# ─── Pre-compute fixed boolean series ─────────────────────────────────────────
ema_bear      = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
rsi_falling   = df["RSI"] < df["RSI"].shift(1)
rsi_short_ok  = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
momentum_ok   = df["Close"] < df["Close"].shift(MOMENTUM_BARS)
is_panic      = df["ATR"] > df["ATR_BL"] * PANIC_MULT
session_ok    = (df["ET_HOUR"] >= SESSION_START_ET) & (df["ET_HOUR"] < SESSION_END_ET)
short_recover = (df["Close"] < df["EMA_FAST"]) & (df["Close"] < df["Open"])
atr_floor_ok  = df["ATR"] / df["Close"] >= ATR_FLOOR

# Precompute arrays for fast sim
close_arr = df["Close"].values
high_arr  = df["High"].values
low_arr   = df["Low"].values
atr_arr   = df["ATR"].values
ema_fast_arr  = df["EMA_FAST"].values
vol_ma_arr    = df["VOL_MA"].values
vol_arr       = df["Volume"].values
adx_arr       = df["ADX"].values
di_minus_arr  = df["DI_MINUS"].values

ema_bear_arr     = ema_bear.values
rsi_falling_arr  = rsi_falling.values
rsi_short_ok_arr = rsi_short_ok.values
momentum_ok_arr  = momentum_ok.values
is_panic_arr     = is_panic.values
session_ok_arr   = session_ok.values
short_recover_arr= short_recover.values
atr_floor_ok_arr = atr_floor_ok.values

n = len(df)

# ─── Fast simulation kernel ───────────────────────────────────────────────────
def run_sim(signal_arr, tp_mult, trail_dist, max_bars, risk_pct):
    equity        = INITIAL_CAPITAL
    pos           = None
    wins = losses = 0
    gross_profit = gross_loss = 0.0
    eq_list      = np.empty(n)
    consec_losses = 0
    cooldown_bars = 0
    bars_in_trade = 0

    for i in range(n):
        eq_list[i] = equity
        cl = close_arr[i]; hi = high_arr[i]; lo = low_arr[i]; atr = atr_arr[i]
        if atr == 0 or np.isnan(atr):
            continue

        sd = atr * SL_MULT

        if pos is not None:
            bars_in_trade += 1
            if lo < pos[3]:          # update best
                pos[3] = lo
            if pos[3] <= pos[5]:     # trail activation
                new_sl = pos[3] + pos[6]
                if new_sl < pos[2]:
                    pos[2] = new_sl

            mb_exit = (max_bars > 0 and bars_in_trade >= max_bars)
            htp = (not mb_exit) and (lo  <= pos[1])
            hsl = (not mb_exit) and (hi >= pos[2])

            if mb_exit or htp or hsl:
                xp      = cl if mb_exit else (pos[1] if htp else pos[2])
                pnl_pct = (pos[0] - xp) / pos[0]
                dp      = pnl_pct * pos[4] - pos[4] * COMMISSION_PCT * 2
                equity += dp
                if dp > 0:
                    wins += 1; gross_profit += dp; consec_losses = 0
                else:
                    losses += 1; gross_loss += dp
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                pos = None; bars_in_trade = 0

        if pos is None:
            if cooldown_bars > 0:
                cooldown_bars -= 1
            elif signal_arr[i]:
                notl = min(equity * risk_pct / sd * cl, equity * 5.0)
                # [entry, tp, sl, best, notional, trail_act_px, trail_dist_fixed]
                pos = [cl, cl - atr * tp_mult, cl + sd, cl, notl,
                       cl - atr * TRAIL_ACT, atr * trail_dist]
                bars_in_trade = 0

    trades = wins + losses
    if trades < 8:
        return None
    final  = equity
    net    = (final - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    wr     = wins / trades * 100
    pf     = gross_profit / abs(gross_loss) if gross_loss != 0 else float("inf")
    roll_max = np.maximum.accumulate(eq_list)
    dd_arr   = (eq_list - roll_max) / np.where(roll_max > 0, roll_max, 1) * 100
    max_dd   = dd_arr.min()
    calmar   = net / abs(max_dd) if max_dd != 0 else float("inf")
    return trades, wr, pf, net, final, max_dd, calmar

# ─── Sweep loop ──────────────────────────────────────────────────────────────
OUT = Path(__file__).parent / "sweep_stage5_results.csv"
fieldnames = ["adx","pb_pct","vol_mult","min_body","tp_mult","trail_dist",
              "max_bars","risk_pct","trades","wr","pf","net_pct","final_eq","max_dd","calmar"]

written = 0
best_net = 0.0
GRID = list(itertools.product(
    ADX_VALS, PB_VALS, VOL_VALS, MIN_BODY_VALS,
    TP_VALS, RISK_VALS, TRAIL_DIST_VALS, MAX_BARS_VALS
))

import csv
with open(OUT, "w", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()

    for i, (adx, pb, vol, mb_thresh, tp, risk, tdist, mxb) in enumerate(GRID):
        if i % 1000 == 0:
            print(f"  {i:>6}/{total}  best_net={best_net:.2f}%", flush=True)

        tol = pb / 100.0

        # Signal-dependent arrays
        pb_tol_dn     = ema_fast_arr[:-1] * (1.0 - tol)
        short_pullback_raw = np.empty(n, dtype=bool); short_pullback_raw[:] = False
        short_pullback_raw[1:] = high_arr[1:] >= pb_tol_dn   # shifted: prev bar high

        # Recompute using prev-bar EMA (already shifted in original code via shift(1))
        # The original uses High.shift(1) >= EMA_FAST.shift(1) * (1-tol)
        # We already pre-computed from the raw arrays above
        high_prev    = np.empty(n, dtype=float); high_prev[0] = np.nan
        high_prev[1:] = high_arr[:-1]
        ema_prev     = np.empty(n, dtype=float); ema_prev[0] = np.nan
        ema_prev[1:] = ema_fast_arr[:-1]
        short_pullback_arr = high_prev >= ema_prev * (1.0 - tol)

        vol_ok_arr = vol_arr >= vol_ma_arr * vol
        adx_ok_arr = adx_arr > adx
        body_num = np.abs(close_arr - df["Open"].values)
        body_ok_arr = body_num / np.where(atr_arr > 0, atr_arr, 1e-10) >= mb_thresh

        signal = (short_pullback_arr & short_recover_arr & body_ok_arr &
                  ema_bear_arr & rsi_falling_arr & rsi_short_ok_arr &
                  vol_ok_arr & adx_ok_arr & momentum_ok_arr &
                  session_ok_arr & ~is_panic_arr & atr_floor_ok_arr)

        res = run_sim(signal, tp, tdist, mxb, risk / 100.0)
        if res is None:
            continue

        trades, wr, pf, net, final, max_dd, calmar = res
        if net > best_net:
            best_net = net
        writer.writerow({
            "adx": adx, "pb_pct": pb, "vol_mult": vol, "min_body": mb_thresh,
            "tp_mult": tp, "trail_dist": tdist, "max_bars": mxb, "risk_pct": risk,
            "trades": trades, "wr": round(wr,1), "pf": round(pf,3),
            "net_pct": round(net,2), "final_eq": round(final,2),
            "max_dd": round(max_dd,2), "calmar": round(calmar,3)
        })
        written += 1

print(f"\nDone. {written} valid combos written → {OUT.name}")
print(f"Best net_pct found: {best_net:.2f}%")

# ─── Quick leaderboard ────────────────────────────────────────────────────────
res_df = pd.read_csv(OUT)
print(f"\n=== TOP 10 by WR then net_pct (WR≥80%) ===")
q = res_df[(res_df["wr"] >= 80)].sort_values(["net_pct","calmar"], ascending=False)
print(q.head(10)[["adx","pb_pct","vol_mult","min_body","risk_pct","tp_mult","trail_dist","max_bars","trades","wr","net_pct","max_dd","calmar"]].to_string())

print(f"\n=== TOP 10 ALL by net_pct ===")
print(res_df.sort_values("net_pct", ascending=False).head(10)[
    ["adx","pb_pct","vol_mult","min_body","risk_pct","tp_mult","trail_dist","max_bars","trades","wr","net_pct","max_dd","calmar"]].to_string())
