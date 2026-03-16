"""Stage-4 sweep for APM v2 BTCUSD 10m — targeting 20%+ net profit
Fixed base: Stage-3 winner (ADX=20, pb=0.30, vol=0.7, atr_floor=0.001,
            panic=1.5, min_body=0.20, sl=2.0, trail_act=3.5, trail_dist=0.3,
            tp=6.0, max_bars=30)

Approach: two signal configs (quality + slightly relaxed), then sweep
          exit params across wider ranges than prior stages.

Signal presets swept:
  A — Quality  : ADX=20, pb=0.30, vol=0.7, atr_floor=0.001
  B — Relaxed  : ADX=15, pb=0.40, vol=0.5, atr_floor=0.0

Exit dimensions swept:
  tp_mult    : [6.0, 7.0, 8.0, 9.0, 10.0]
  risk_pct   : [1.0, 1.5, 2.0, 2.5]
  trail_act  : [3.0, 3.5, 4.0, 4.5]
  trail_dist : [0.1, 0.2, 0.3, 0.4, 0.5]
  max_bars   : [0, 20, 25, 30]
  sl_mult    : [2.0, 2.5, 3.0]

Total: 2 × 5×4×4×5×4×3 = 9,600 combos
"""

import subprocess, sys
for pkg in ["alpaca-py", "pandas", "numpy"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import pandas as pd
import numpy as np
import pytz, csv, itertools
from datetime import datetime, timezone
from pathlib import Path
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

_ET = pytz.timezone("America/New_York")

# ─── Alpaca credentials ───────────────────────────────────────────────────────
ALPACA_KEY    = "PKNIYXYVLHKHF43IIEUQIA42DJ"
ALPACA_SECRET = "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u"

TICKER         = "BTCUSD"
BACKTEST_END   = datetime(2026, 3, 14, tzinfo=timezone.utc)
BACKTEST_START = datetime(2025, 3, 14, tzinfo=timezone.utc)

# ─── Fixed indicator params ───────────────────────────────────────────────────
EMA_FAST         = 21;  EMA_MID  = 50;  EMA_SLOW = 200
ADX_LEN          = 14;  RSI_LEN  = 14;  ATR_LEN  = 14;  VOL_LEN = 20
ATR_BL_LEN       = 60
MIN_BODY         = 0.20   # matches Pine Script v2.3
PANIC_MULT       = 1.5
RSI_LO_S         = 32.0;  RSI_HI_S = 58.0
SESSION_START_ET = 9;     SESSION_END_ET = 14
MOMENTUM_BARS        = 5
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
COMMISSION_PCT   = 0.0006
INITIAL_CAPITAL  = 10_000.0

# ─── Signal presets ───────────────────────────────────────────────────────────
SIGNAL_PRESETS = [
    {"name": "quality",  "adx": 20, "pb": 0.30, "vol": 0.7, "atr_floor": 0.001},
    {"name": "relaxed",  "adx": 15, "pb": 0.40, "vol": 0.5, "atr_floor": 0.0},
]

# ─── Exit sweep grid ──────────────────────────────────────────────────────────
TP_VALS        = [6.0, 7.0, 8.0, 9.0, 10.0]
RISK_VALS      = [1.0, 1.5, 2.0, 2.5]
TRAIL_ACT_VALS = [3.0, 3.5, 4.0, 4.5]
TRAIL_DIST_VALS= [0.1, 0.2, 0.3, 0.4, 0.5]
MAX_BARS_VALS  = [0, 20, 25, 30]
SL_VALS        = [2.0, 2.5, 3.0]

total = len(SIGNAL_PRESETS) * len(TP_VALS) * len(RISK_VALS) * len(TRAIL_ACT_VALS) * len(TRAIL_DIST_VALS) * len(MAX_BARS_VALS) * len(SL_VALS)
print(f"Stage-4 sweep: {total:,} combos  ({len(SIGNAL_PRESETS)} signal presets × exit grid)")

# ─── Fetch + resample ─────────────────────────────────────────────────────────
print(f"\nFetching {TICKER} 5m ({BACKTEST_START.date()} → {BACKTEST_END.date()}) ...")
client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
bars = client.get_stock_bars(StockBarsRequest(
    symbol_or_symbols=TICKER,
    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
    start=BACKTEST_START, end=BACKTEST_END,
    feed=DataFeed.IEX,
))
raw = bars.df.reset_index()
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(0)
raw = raw.rename(columns={"timestamp": "time"}).set_index("time")
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw = raw[["open","high","low","close","volume"]].rename(columns=str.title)
raw = raw[raw["Volume"] > 0].dropna()
raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample("10min", label="left", closed="left", origin="start_day").agg(
    {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
)
df = df[df["Volume"] > 0].dropna()
print(f"  5m bars: {len(raw)}  →  10m bars: {len(df)}")

# ─── Compute indicators ───────────────────────────────────────────────────────
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

up_move  = df["High"].diff()
dn_move  = -df["Low"].diff()
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

# ─── Fixed signal components ──────────────────────────────────────────────────
ema_bear      = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
rsi_falling   = df["RSI"] < df["RSI"].shift(1)
rsi_short_ok  = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
body          = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, 1e-10)
body_ok       = body >= MIN_BODY
is_panic      = df["ATR"] > df["ATR_BL"] * PANIC_MULT
momentum_ok   = df["Close"] < df["Close"].shift(MOMENTUM_BARS)
session_ok    = (df["ET_HOUR"] >= SESSION_START_ET) & (df["ET_HOUR"] < SESSION_END_ET)
short_recover = (df["Close"] < df["EMA_FAST"]) & (df["Close"] < df["Open"])
atr_ratio     = df["ATR"] / df["Close"]

# ─── Build signal masks for each preset ──────────────────────────────────────
print("\nBuilding signal masks ...")
signal_masks = {}
for preset in SIGNAL_PRESETS:
    pb_tol_dn   = df["EMA_FAST"].shift(1) * (1.0 - preset["pb"] / 100.0)
    short_pb    = df["High"].shift(1) >= pb_tol_dn
    vol_ok      = df["Volume"] >= df["VOL_MA"] * preset["vol"]
    is_trending = df["ADX"] > preset["adx"]
    atr_fl_ok   = atr_ratio >= preset["atr_floor"]
    sig = (short_pb & short_recover & body_ok & ema_bear &
           rsi_falling & rsi_short_ok & vol_ok & is_trending &
           momentum_ok & session_ok & ~is_panic & atr_fl_ok)
    n = int(sig.sum())
    print(f"  {preset['name']:10s}  signals={n}")
    signal_masks[preset["name"]] = sig

# ─── Fast simulation ──────────────────────────────────────────────────────────
close_arr = df["Close"].values.tolist()
high_arr  = df["High"].values.tolist()
low_arr   = df["Low"].values.tolist()
atr_arr   = df["ATR"].values.tolist()
n_bars    = len(close_arr)

def run_sim(sig_mask, sl_mult, tp_mult, trail_act, trail_dist, max_bars, risk_pct):
    sig = sig_mask.values.tolist()
    equity = INITIAL_CAPITAL; pos = None
    trades_net = []; eq_peak = INITIAL_CAPITAL; max_dd = 0.0
    consec_losses = 0; cooldown_bars = 0; bars_in_trade = 0

    for i in range(n_bars):
        c = close_arr[i]; h = high_arr[i]; lo = low_arr[i]; a = atr_arr[i]
        if a == 0 or a != a:
            if equity > eq_peak: eq_peak = equity
            continue
        sd = a * sl_mult

        if pos is not None:
            bars_in_trade += 1
            if lo < pos[4]: pos[4] = lo
            if pos[4] <= pos[5]:
                new_sl = pos[4] + pos[6]
                if new_sl < pos[1]: pos[1] = new_sl

            mb_exit = max_bars > 0 and bars_in_trade >= max_bars
            htp = (not mb_exit) and (lo  <= pos[2])
            hsl = (not mb_exit) and (h   >= pos[1])

            if mb_exit or htp or hsl:
                xp  = c if mb_exit else (pos[2] if htp else pos[1])
                pnl_pct = (pos[0] - xp) / pos[0]
                dp  = pnl_pct * pos[3] - pos[3] * COMMISSION_PCT * 2
                equity += dp
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
                trail_act_px  = c - a * trail_act
                trail_dist_px = a * trail_dist
                # [entry, sl, tp, notional, best_low, trail_activate_px, trail_dist_fixed]
                pos = [c, c + sd, c - a * tp_mult, notl, c, trail_act_px, trail_dist_px]
                bars_in_trade = 0

        if equity > eq_peak: eq_peak = equity
        dd = (equity - eq_peak) / eq_peak * 100
        if dd < max_dd: max_dd = dd

    if not trades_net: return None
    n_t  = len(trades_net)
    wins = sum(1 for x in trades_net if x > 0)
    wr   = wins / n_t * 100
    gp   = sum(x for x in trades_net if x > 0)
    gl   = sum(x for x in trades_net if x <= 0)
    pf   = gp / abs(gl) if gl != 0 else float("inf")
    net  = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    calmar = (net / abs(max_dd)) if max_dd != 0 else float("inf")
    return n_t, wr, pf, net, equity, max_dd, calmar

# ─── Run sweep ────────────────────────────────────────────────────────────────
print(f"\nRunning {total:,} combos ...")
results = []
done = 0

for preset in SIGNAL_PRESETS:
    sig = signal_masks[preset["name"]]
    pname = preset["name"]
    for tp, risk, tact, tdist, mb, sl in itertools.product(
            TP_VALS, RISK_VALS, TRAIL_ACT_VALS, TRAIL_DIST_VALS, MAX_BARS_VALS, SL_VALS):
        done += 1
        res = run_sim(sig, sl, tp, tact, tdist, mb, risk / 100.0)
        if res is None: continue
        n_t, wr, pf, net, eq, max_dd, calmar = res
        if n_t >= 8:
            results.append({
                "preset": pname,
                "adx": preset["adx"], "pb_pct": preset["pb"],
                "vol_mult": preset["vol"], "atr_floor": preset["atr_floor"],
                "sl_mult": sl, "tp_mult": tp,
                "trail_act": tact, "trail_dist": tdist,
                "max_bars": mb, "risk_pct": risk,
                "trades": n_t, "wr": round(wr, 1), "pf": round(pf, 3),
                "net_pct": round(net, 2), "final_eq": round(eq, 2),
                "max_dd": round(max_dd, 2), "calmar": round(calmar, 3),
            })
        if done % 1000 == 0:
            best_so_far = max((r["net_pct"] for r in results), default=0)
            print(f"  {done:>6,}/{total:,}  |  {len(results)} qualifying  |  best={best_so_far:+.2f}%", flush=True)

print(f"\nSweep complete. {len(results)} combos with ≥8 trades")

# ─── Save + report ────────────────────────────────────────────────────────────
out_csv = Path(__file__).parent / "sweep_stage4_results.csv"
if not results:
    print("No qualifying results. Relax filters and retry.")
else:
    rdf = pd.DataFrame(results).sort_values("net_pct", ascending=False)
    rdf.to_csv(out_csv, index=False)
    print(f"Saved → {out_csv.name}")

    print(f"\n{'='*80}")
    print(f"  TOP 15 by net_pct (≥8 trades)")
    print(f"{'='*80}")
    print(rdf.head(15).to_string(index=False))

    # Highlight configs > 20%
    above20 = rdf[rdf["net_pct"] >= 20.0]
    print(f"\n  Configs ≥ 20% net: {len(above20)}")
    if not above20.empty:
        print(f"\n{'='*80}")
        print(f"  BEST ≥20% by Calmar (quality + return)")
        print(f"{'='*80}")
        print(above20.sort_values("calmar", ascending=False).head(10).to_string(index=False))

    best = rdf.iloc[0]
    print(f"\n{'='*80}")
    print(f"  OPTIMAL CONFIG")
    print(f"{'='*80}")
    print(f"  preset     : {best['preset']}")
    print(f"  adx_thresh : {best['adx']}")
    print(f"  pb_pct     : {best['pb_pct']}")
    print(f"  vol_mult   : {best['vol_mult']}")
    print(f"  atr_floor  : {best['atr_floor']}")
    print(f"  sl_mult    : {best['sl_mult']}")
    print(f"  tp_mult    : {best['tp_mult']}")
    print(f"  trail_act  : {best['trail_act']}")
    print(f"  trail_dist : {best['trail_dist']}")
    print(f"  max_bars   : {best['max_bars']}")
    print(f"  risk_pct   : {best['risk_pct']}")
    print(f"  → trades={best['trades']}  WR={best['wr']}%  PF={best['pf']}  net={best['net_pct']:+.2f}%  MaxDD={best['max_dd']}%  Calmar={best['calmar']}")
