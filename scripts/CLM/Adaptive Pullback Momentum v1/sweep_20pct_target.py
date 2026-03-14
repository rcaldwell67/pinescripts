# ─────────────────────────────────────────────────────────────────────────────
# APM v1.0 — CLM 5m  ·  20%+ Target Sweep
#
# Anchors the best signal parameters from sweep12_s2_signal/s3_trail:
#   ADX=18, PB=0.25%, VOL=0.3, ATR_FLOOR=0.1%, MACRO_EMA=400
# Then sweeps:
#   RISK_PCT  : 1.0%, 1.5%, 2.0%, 2.5%, 3.0%
#   SL_MULT   : 2.0, 3.0, 4.0, 5.0
#   TP_MULT   : 4.0, 5.0, 6.0, 7.0, 8.0
#   TRAIL_ACT : 2.0, 2.5, 3.0, 3.5
#   TRAIL_DIST: 0.1, 0.2, 0.3, 0.4
#
# Sort: net_pct descending.  Min 8 trades.  Saves top-100 results.
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys, itertools
for pkg in ["alpaca-py", "pandas", "numpy", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import pandas as pd
import numpy as np
import pytz, warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

_ET = pytz.timezone("America/New_York")

# ─── Alpaca credentials ────────────────────────────────────────────────────────
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
ALPACA_KEY    = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "PKNIYXYVLHKHF43IIEUQIA42DJ")
ALPACA_SECRET = os.environ.get("ALPACA_PAPER_API_SECRET") or os.environ.get("ALPACA_API_SECRET", "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u")

TICKER          = "CLM"
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
MIN_TRADES      = 8

# ── Fixed indicator periods ────────────────────────────────────────────────────
EMA_FAST = 21; EMA_MID = 50; EMA_SLOW = 200
ADX_LEN = 14; RSI_LEN = 14; ATR_LEN = 14; VOL_LEN = 20; ATR_BL_LEN = 60

# ── Best-found signal params (locked from stage-2/3/4 sweeps) ─────────────────
ADX_THRESH  = 18     # will be swept below
PB_PCT      = 0.25   # will be swept below
VOL_MULT    = 0.3
ATR_FLOOR   = 0.001   # 0.1%
PANIC_MULT  = 1.5
MIN_BODY    = 0.15
EMA_SLOPE_BARS = 3
MOMENTUM_BARS  = 5
RSI_LO_S = 30; RSI_HI_S = 58
SESSION_S = 9; SESSION_E = 14
MACRO_EMA = 0         # off

CONSEC_LIMIT = 2; CONSEC_COOL = 1

# ── Sweep grid ─────────────────────────────────────────────────────────────────
RISK_VALS    = [0.010, 0.015, 0.020, 0.025, 0.030, 0.035]
SL_VALS      = [2.0, 3.0, 4.0, 5.0]
TP_VALS      = [4.0, 5.0, 6.0, 7.0, 8.0]
TRAIL_A_VALS = [2.0, 2.5, 3.0, 3.5]
TRAIL_D_VALS = [0.1, 0.2, 0.3, 0.4]
ADX_VALS     = [12, 15, 18]
PB_VALS      = [0.25, 0.30, 0.40, 0.50]
OUT_FILE     = "sweep_20pct_nommacro.csv"

# ─── Download ─────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} 5m via Alpaca (12 months)…")
client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
req = StockBarsRequest(
    symbol_or_symbols=TICKER,
    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
    start=datetime(2025, 3, 12, tzinfo=timezone.utc),
    end=datetime(2026, 3, 12, tzinfo=timezone.utc),
    feed=DataFeed.IEX,
)
bars = client.get_stock_bars(req)
raw = bars.df.reset_index(level=0, drop=True)
raw = raw.rename(columns={"open":"Open","high":"High","low":"Low",
                           "close":"Close","volume":"Volume"})
raw = raw[["Open","High","Low","Close","Volume"]].copy()
raw = raw[raw["Volume"] > 0].dropna()
raw.index = pd.to_datetime(raw.index, utc=True).tz_convert(_ET)
print(f"Bars: {len(raw)}  |  {raw.index[0]} → {raw.index[-1]}")

# ─── Build indicators (once — only ATR/volume/RSI/EMA vary with fixed periods) -
df = raw.copy()
df["EF"]    = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EM"]    = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["ES"]    = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()
if MACRO_EMA > 0:
    df["MACRO"] = df["Close"].ewm(span=MACRO_EMA, adjust=False).mean()

delta = df["Close"].diff()
g = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
l = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + g / l.replace(0, 1e-10)))

hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up = df["High"] - df["High"].shift(1)
dn = df["Low"].shift(1) - df["Low"]
pdm = np.where((up > dn) & (up > 0), up, 0.0)
ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
sp = pd.Series(pdm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
sm = pd.Series(ndm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI+"] = 100 * sp / df["ATR"].replace(0, 1e-10)
df["DI-"] = 100 * sm / df["ATR"].replace(0, 1e-10)
dx = 100 * (df["DI+"] - df["DI-"]).abs() / (df["DI+"] + df["DI-"]).replace(0, 1e-10)
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()
df.dropna(inplace=True)
df["ET_HOUR"] = df.index.hour

# pre-compute components that don't depend on adx_thresh or pb_pct
ema_bear   = (df["EF"] < df["EM"]) & (df["EM"] < df["ES"])
ema_sl_dn  = df["EF"] < df["EF"].shift(EMA_SLOPE_BARS)
rsi_fall   = df["RSI"] < df["RSI"].shift(1)
rsi_ok_s   = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
vol_ok     = df["Volume"] >= df["VOL_MA"] * VOL_MULT
body_ok    = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, 1e-10) >= MIN_BODY
not_panic  = df["ATR"] <= df["ATR_BL"] * PANIC_MULT
atr_fl_ok  = df["ATR"] / df["Close"] >= ATR_FLOOR
mom_ok     = df["Close"] < df["Close"].shift(MOMENTUM_BARS)
session    = (df["ET_HOUR"] >= SESSION_S) & (df["ET_HOUR"] < SESSION_E)
macro_ok   = df["Close"] < df["MACRO"] if MACRO_EMA > 0 else pd.Series(True, index=df.index)

# base mask (everything except adx_thresh and pb_pct)
base_mask  = ema_bear & ema_sl_dn & rsi_fall & rsi_ok_s & vol_ok & body_ok & not_panic & atr_fl_ok & mom_ok & session & macro_ok

# pre-compute masks for each ADX_THRESH
adx_masks = {thresh: (df["ADX"] > thresh) & base_mask for thresh in ADX_VALS}

# pre-compute pullback masks for each PB_PCT
def pb_mask(pb_pct_val):
    tol   = pb_pct_val / 100.0
    pb_dn = df["EF"].shift(1) * (1.0 - tol)
    return (df["High"].shift(1) >= pb_dn) & (df["Close"] < df["EF"]) & (df["Close"] < df["Open"])

pb_masks = {pb: pb_mask(pb) for pb in PB_VALS}

# Combined signal cache: (adx_thresh, pb_pct) → signal boolean array
sig_cache = {}
for adx_t in ADX_VALS:
    for pb_v in PB_VALS:
        sig_cache[(adx_t, pb_v)] = (adx_masks[adx_t] & pb_masks[pb_v]).values.astype(bool)

print("Signal counts by (ADX, PB%):")
for (adx_t, pb_v), mask in sig_cache.items():
    print(f"  ADX={adx_t:2d}  PB={pb_v:.2f}%  →  {mask.sum()} signals")

# pre-extract arrays for fast simulation
CLOSE = df["Close"].values
HIGH  = df["High"].values
LOW   = df["Low"].values
ATR_V = df["ATR"].values
N     = len(df)

# ─── Simulator (short-only) ────────────────────────────────────────────────────
def simulate(sl_m, tp_m, trail_act, trail_dist, risk_pct, sig):
    equity = INITIAL_CAPITAL
    pos    = None
    trades = 0
    wins   = 0
    gross_w = gross_l = 0.0
    peak    = equity
    max_dd  = 0.0
    consec_loss = 0

    for i in range(N):
        if pos is not None:
            if LOW[i] <= pos["best"]:
                pos["best"] = LOW[i]
            # trailing stop update
            if pos["best"] <= pos["trail_px"]:
                new_sl = pos["best"] + pos["trail_d"]
                if new_sl < pos["sl"]:
                    pos["sl"] = new_sl

            hit_tp  = LOW[i]  <= pos["tp"]
            hit_sl  = HIGH[i] >= pos["sl"]
            bar_cnt = i - pos["entry_i"]
            hit_mb  = pos["max_bars"] > 0 and bar_cnt >= pos["max_bars"]

            if hit_tp or hit_sl or hit_mb:
                xp = pos["tp"] if hit_tp else (pos["sl"] if hit_sl else CLOSE[i])
                pnl = (pos["entry"] - xp) / pos["entry"]
                dp  = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                trades += 1
                if dp > 0:
                    wins += 1; gross_w += dp
                else:
                    gross_l += abs(dp); consec_loss += 1
                if not hit_sl and not hit_mb:
                    consec_loss = 0
                peak  = max(peak, equity)
                dd    = (peak - equity) / peak
                max_dd = max(max_dd, dd)
                pos = None

        if pos is None and sig[i]:
            if consec_loss >= CONSEC_LIMIT:
                consec_loss -= CONSEC_COOL
                continue
            atr = ATR_V[i]; c = CLOSE[i]
            sd  = atr * sl_m
            notional = min(equity * risk_pct / sd * c, equity * 5.0)
            pos = {
                "entry":    c,
                "entry_i":  i,
                "sl":       c + sd,
                "tp":       c - atr * tp_m,
                "best":     c,
                "notional": notional,
                "trail_px": c - atr * trail_act,
                "trail_d":  atr * trail_dist,
                "max_bars": 0,
            }

    net_pct = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    wr      = wins / trades * 100 if trades > 0 else 0.0
    pf      = gross_w / gross_l if gross_l > 0 else (float("inf") if gross_w > 0 else 0.0)
    calmar  = net_pct / (max_dd * 100) if max_dd > 0 else 0.0
    return trades, wr, pf, net_pct, max_dd * 100, calmar


# ─── Sweep ────────────────────────────────────────────────────────────────────
grid  = list(itertools.product(ADX_VALS, PB_VALS, SL_VALS, TP_VALS, TRAIL_A_VALS, TRAIL_D_VALS, RISK_VALS))
total = len(grid)
print(f"Sweep: {total} combinations…")

rows = []
for idx, (adx_t, pb_v, sl_m, tp_m, ta, td, rp) in enumerate(grid):
    if idx % 2000 == 0:
        print(f"  {idx}/{total}", end="\r", flush=True)
    sig = sig_cache[(adx_t, pb_v)]
    trades, wr, pf, net, dd, calmar = simulate(sl_m, tp_m, ta, td, rp, sig)
    if trades >= MIN_TRADES:
        rows.append({
            "adx_thresh": adx_t,
            "pb_pct":     pb_v,
            "risk_pct":   round(rp * 100, 1),
            "sl_mult":    sl_m,
            "tp_mult":    tp_m,
            "trail_act":  ta,
            "trail_dist": td,
            "trades":     trades,
            "wr":         round(wr, 1),
            "pf":         round(pf, 3),
            "net_pct":    round(net, 2),
            "max_dd":     round(dd, 2),
            "calmar":     round(calmar, 3),
        })

res = pd.DataFrame(rows).sort_values("net_pct", ascending=False)
above20 = res[res["net_pct"] >= 20.0]
print(f"\nTotal valid combos: {len(res)}  |  Above 20% net: {len(above20)}")
print("\n─── TOP 20 RESULTS ───────────────────────────────")
print(res.head(20).to_string(index=False))
if not above20.empty:
    print(f"\n─── ABOVE 20% NET ({len(above20)} rows) ─────────────────")
    print(above20.head(30).to_string(index=False))

res.head(100).to_csv(OUT_FILE, index=False)
print(f"\nTop-100 saved → {OUT_FILE}")

# Print best row details
if not res.empty:
    best = res.iloc[0]
    print(f"""
╔══ BEST RESULT ══════════════════════════════════════════════╗
  Net profit : {best.net_pct:+.2f}%
  Win rate   : {best.wr:.1f}%      Profit factor: {best.pf:.3f}
  Max DD     : -{best.max_dd:.2f}%   Calmar: {best.calmar:.3f}
  Trades     : {int(best.trades)}
  ──────────────────────────────────────────────────────────
  ADX thresh : {int(best.adx_thresh)}    PB tol: {best.pb_pct:.2f}%
  RISK_PCT   : {best.risk_pct:.1f}%
  SL×{best.sl_mult:.1f}   TP×{best.tp_mult:.1f}   Trail act×{best.trail_act:.1f}  dist×{best.trail_dist:.1f}
╚═════════════════════════════════════════════════════════════╝
""")
