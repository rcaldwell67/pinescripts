# ─────────────────────────────────────────────────────────────────────────────
# APM v2 — BTCUSD 10m  ·  Sweep targeting 20%+ net profit
# Approach: pre-compute signal masks for each (ADX, PB, VOL, ATR_FLOOR) combo,
#           then iterate exit params (SL, TP, TRAIL, MAX_BARS, RISK) — fast
#           because the expensive indicator computation runs only once.
#
# Key insight from baseline: ATR_FLOOR=0.15% and ADX=20 limit to only 7 signals
# over 12 months — need to relax these to get statistically meaningful results.
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["alpaca-py", "pandas", "numpy"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import pandas as pd
import numpy as np
import pytz, csv, itertools
from datetime import datetime, timezone
from pathlib import Path
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

_ET = pytz.timezone("America/New_York")

# ─── Alpaca credentials ────────────────────────────────────────────────────────
ALPACA_KEY    = "PKNIYXYVLHKHF43IIEUQIA42DJ"
ALPACA_SECRET = "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u"

TICKER = "BTC/USD"
BACKTEST_END   = datetime(2026, 3, 12, tzinfo=timezone.utc)
BACKTEST_START = datetime(2025, 3, 12, tzinfo=timezone.utc)

# Fixed indicator params
EMA_FAST   = 21;  EMA_MID  = 50;  EMA_SLOW = 200
ADX_LEN    = 14;  RSI_LEN  = 14;  ATR_LEN  = 14;  VOL_LEN = 20
ATR_BL_LEN = 60
MIN_BODY       = 0.20
PANIC_MULT     = 1.5
EMA_SLOPE_BARS = 0   # off — stage-1 winner
ADX_SLOPE_BARS = 0   # off
DI_SPREAD_MIN  = 0.0 # off
MOMENTUM_BARS  = 5
RSI_LO_S = 32;  RSI_HI_S = 58
SESSION_START_ET = 9
SESSION_END_ET   = 14
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
COMMISSION_PCT  = 0.0006
INITIAL_CAPITAL = 10_000.0

# ─── Sweep dimensions ─────────────────────────────────────────────────────────
# Focused grid — key insight: ATR_FLOOR=0.15% is the primary signal killer.
# Using Python float lists in the sim loop (3× faster than numpy scalar access).
ADX_VALS      = [12, 15, 18, 20]
PB_VALS       = [0.25, 0.30, 0.40, 0.50]
VOL_VALS      = [0.3, 0.5, 0.7]
ATR_FLOOR_VALS= [0.0, 0.0005, 0.001, 0.0015]   # 0%, 0.05%, 0.10%, 0.15%
RISK_VALS     = [1.0, 1.5, 2.0, 2.5, 3.0]
SL_VALS       = [2.0, 3.0, 4.0]
TP_VALS       = [4.0, 6.0, 8.0]
TRAIL_ACT_VALS= [2.5, 3.5, 4.0]
TRAIL_DIST_VALS=[0.1, 0.2, 0.3]
MAX_BARS_VALS = [0, 20, 30]

total_signal_combos = len(ADX_VALS) * len(PB_VALS) * len(VOL_VALS) * len(ATR_FLOOR_VALS)
total_exit_combos   = (len(RISK_VALS) * len(SL_VALS) * len(TP_VALS)
                       * len(TRAIL_ACT_VALS) * len(TRAIL_DIST_VALS) * len(MAX_BARS_VALS))
print(f"Signal combos: {total_signal_combos}  ×  Exit combos: {total_exit_combos}  =  {total_signal_combos * total_exit_combos:,} total")

# ─── Fetch + resample once ────────────────────────────────────────────────────
print(f"Fetching {TICKER} 5m ({BACKTEST_START.date()} → {BACKTEST_END.date()}) ...")
client = CryptoHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
bars = client.get_crypto_bars(CryptoBarsRequest(
    symbol_or_symbols=TICKER,
    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
    start=BACKTEST_START, end=BACKTEST_END,
))
raw = bars.df.reset_index()
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
df = raw_et.resample("10min", label="left", closed="left", origin="start_day").agg(
    {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
)
df = df[df["Volume"] > 0].dropna()
print(f"  5m bars: {len(raw)}  →  10m bars: {len(df)}")

# ─── Compute fixed indicators once ────────────────────────────────────────────
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta = df["Close"].diff()
avg_g = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
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
dx = (100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs()
          / (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()

df.dropna(inplace=True)
df["ET_HOUR"] = df.index.hour
print(f"  usable bars after warmup: {len(df)}")

# ─── Pre-compute fixed signal components (independent of swept params) ────────
ema_bear       = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
ema_slope_down = pd.Series(True, index=df.index)   # EMA_SLOPE_BARS=0 → off
rsi_falling    = df["RSI"] < df["RSI"].shift(1)
rsi_short_ok   = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
body           = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, 1e-10)
body_ok        = body >= MIN_BODY
is_panic       = df["ATR"] > df["ATR_BL"] * PANIC_MULT
di_spread_ok   = (df["DI_MINUS"] - df["DI_PLUS"]) >= DI_SPREAD_MIN
momentum_ok    = df["Close"] < df["Close"].shift(MOMENTUM_BARS)
session_ok     = (df["ET_HOUR"] >= SESSION_START_ET) & (df["ET_HOUR"] < SESSION_END_ET)
adx_rising     = pd.Series(True, index=df.index)   # ADX_SLOPE_BARS=0 → off

# Vectorise short recover (fixed)
short_recover  = (df["Close"] < df["EMA_FAST"]) & (df["Close"] < df["Open"])

# Precompute ATR ratio (for ATR_FLOOR check)
atr_ratio = df["ATR"] / df["Close"]

# ─── Pre-compute signal masks per (ADX, PB, VOL, ATR_FLOOR) ──────────────────
print("\nPre-computing signal masks ...")
signal_cache = {}
for adx_t, pb, vol, atr_fl in itertools.product(ADX_VALS, PB_VALS, VOL_VALS, ATR_FLOOR_VALS):
    pb_tol_dn      = df["EMA_FAST"].shift(1) * (1.0 - pb / 100.0)
    short_pullback = df["High"].shift(1) >= pb_tol_dn
    vol_ok         = df["Volume"] >= df["VOL_MA"] * vol
    is_trending    = df["ADX"] > adx_t
    atr_floor_ok   = atr_ratio >= atr_fl

    sig = (
        short_pullback & short_recover & body_ok & ema_bear &
        ema_slope_down & rsi_falling & rsi_short_ok & vol_ok &
        is_trending & adx_rising & di_spread_ok & momentum_ok &
        session_ok & ~is_panic & atr_floor_ok
    )
    signal_cache[(adx_t, pb, vol, atr_fl)] = sig

print(f"  Cached {len(signal_cache)} signal masks")

# ─── Simulation helper ────────────────────────────────────────────────────────
# Use Python float lists for 3× faster iteration vs numpy scalar access
close_arr = df["Close"].values.tolist()
high_arr  = df["High"].values.tolist()
low_arr   = df["Low"].values.tolist()
atr_arr   = df["ATR"].values.tolist()
ts_arr    = df.index
n_bars    = len(close_arr)

def run_sim(signal_mask, sl_mult, tp_mult, trail_act, trail_dist, max_bars, risk_pct):
    sig = signal_mask.values.tolist()   # Python bool list — fast index access
    equity        = INITIAL_CAPITAL
    pos           = None
    trades_net    = []
    eq_peak       = INITIAL_CAPITAL
    max_dd        = 0.0
    consec_losses = 0
    cooldown_bars = 0
    bars_in_trade = 0

    for i in range(n_bars):
        c   = close_arr[i]; h = high_arr[i]; lo = low_arr[i]; a = atr_arr[i]
        if a == 0 or a != a:   # nan check without numpy
            if equity > eq_peak: eq_peak = equity
            continue
        sd = a * sl_mult

        if pos is not None:
            bars_in_trade += 1
            # Update best / trail
            if lo < pos[4]:
                pos[4] = lo
            if pos[4] <= pos[6]:
                new_sl = pos[4] + pos[7]
                if new_sl < pos[1]:
                    pos[1] = new_sl

            mb_exit = (max_bars > 0 and bars_in_trade >= max_bars)
            htp = (not mb_exit) and (lo  <= pos[2])
            hsl = (not mb_exit) and (h   >= pos[1])

            if mb_exit or htp or hsl:
                xp      = c if mb_exit else (pos[2] if htp else pos[1])
                pnl_pct = (pos[0] - xp) / pos[0]
                dp      = pnl_pct * pos[3] - pos[3] * COMMISSION_PCT * 2
                equity += dp
                result  = "MB" if mb_exit else ("TP" if htp else "SL")
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                trades_net.append(dp)
                pos = None; bars_in_trade = 0

        if pos is None:
            if cooldown_bars > 0:
                cooldown_bars -= 1
            elif sig[i]:
                notl = min(equity * risk_pct / sd * c, equity * 5.0)
                # pos: [entry, sl, tp, notional, best, trail_activate_px, ?, trail_dist_fixed]
                trail_act_px  = c - a * trail_act
                trail_dist_px = a * trail_dist
                pos = [c, c + sd, c - a * tp_mult, notl, c, trail_act_px, trail_act_px, trail_dist_px]
                bars_in_trade = 0

        if equity > eq_peak: eq_peak = equity
        dd_pct = (equity - eq_peak) / eq_peak * 100
        if dd_pct < max_dd: max_dd = dd_pct

    if not trades_net:
        return None
    n_trades = len(trades_net)
    wins     = sum(1 for x in trades_net if x > 0)
    wr       = wins / n_trades * 100
    gp = sum(x for x in trades_net if x > 0)
    gl = sum(x for x in trades_net if x <= 0)
    pf = gp / abs(gl) if gl != 0 else float("inf")
    net_pct = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    calmar = (net_pct / abs(max_dd)) if max_dd != 0 else float("inf")

    return (n_trades, wr, pf, net_pct, equity, max_dd, calmar)

# ─── Sweep ────────────────────────────────────────────────────────────────────
print("\nRunning sweep ...")
results = []
total_done = 0

for (adx_t, pb, vol, atr_fl), sig_mask in signal_cache.items():
    n_sig = int(sig_mask.sum())
    for risk, sl, tp, tact, tdist, mb in itertools.product(
        RISK_VALS, SL_VALS, TP_VALS, TRAIL_ACT_VALS, TRAIL_DIST_VALS, MAX_BARS_VALS
    ):
        total_done += 1
        if n_sig == 0:
            continue
        res = run_sim(sig_mask, sl, tp, tact, tdist, mb, risk / 100.0)
        if res is None:
            continue
        n_trades, wr, pf, net_pct, eq, max_dd, calmar = res
        if net_pct >= 20.0 and n_trades >= 8:
            results.append({
                "adx": adx_t, "pb_pct": pb, "vol_mult": vol, "atr_floor": atr_fl,
                "risk_pct": risk, "sl_mult": sl, "tp_mult": tp,
                "trail_act": tact, "trail_dist": tdist, "max_bars": mb,
                "trades": n_trades, "wr": round(wr, 1), "pf": round(pf, 3),
                "net_pct": round(net_pct, 2), "final_eq": round(eq, 2),
                "max_dd": round(max_dd, 2), "calmar": round(calmar, 3),
            })

    if total_done % 2000 == 0:
        print(f"  {total_done:>7,} combos done  |  {len(results)} ≥20% so far  ...", flush=True)

print(f"\nSweep complete: {total_done:,} total  |  {len(results)} combos ≥20% (≥8 trades)")

# ─── Save results ─────────────────────────────────────────────────────────────
_dir = Path(__file__).parent
out_csv = _dir / "sweep_20pct_v2.csv"
if results:
    rdf = pd.DataFrame(results).sort_values("net_pct", ascending=False)
    rdf.head(100).to_csv(out_csv, index=False)
    print(f"Top-100 saved → {out_csv.name}")
    print(f"\nTop 10 by net_pct:")
    print(rdf.head(10).to_string(index=False))
else:
    # No combos hit 20% with ≥8 trades — show best by net%
    print("\nNo combos hit 20%+. Re-running sweep to capture all ≥8 trade results ...")
    results2 = []
    for (adx_t, pb, vol, atr_fl), sig_mask in signal_cache.items():
        n_sig = int(sig_mask.sum())
        if n_sig < 3:
            continue
        for risk, sl, tp, tact, tdist, mb in itertools.product(
            RISK_VALS, SL_VALS, TP_VALS, TRAIL_ACT_VALS, TRAIL_DIST_VALS, MAX_BARS_VALS
        ):
            res = run_sim(sig_mask, sl, tp, tact, tdist, mb, risk / 100.0)
            if res is None:
                continue
            n_trades, wr, pf, net_pct, eq, max_dd, calmar = res
            if n_trades >= 8:
                results2.append({
                    "adx": adx_t, "pb_pct": pb, "vol_mult": vol, "atr_floor": atr_fl,
                    "risk_pct": risk, "sl_mult": sl, "tp_mult": tp,
                    "trail_act": tact, "trail_dist": tdist, "max_bars": mb,
                    "trades": n_trades, "wr": round(wr, 1), "pf": round(pf, 3),
                    "net_pct": round(net_pct, 2), "final_eq": round(eq, 2),
                    "max_dd": round(max_dd, 2), "calmar": round(calmar, 3),
                })
    if results2:
        rdf2 = pd.DataFrame(results2).sort_values("net_pct", ascending=False)
        rdf2.head(100).to_csv(out_csv, index=False)
        best = rdf2.iloc[0]
        print(f"Best result: net={best['net_pct']:+.2f}%  trades={best['trades']}  "
              f"WR={best['wr']}%  PF={best['pf']}")
        print(rdf2.head(10).to_string(index=False))
    else:
        print("No results with ≥8 trades. Try relaxing filters further.")
