"""Stage-3 sweep for APM v5 BTCUSD 10m
Fixed base: Stage-1 + Stage-2 winner (ADX=20, vol=0.7, session_end=14,
            slope=0, di_spread=0, pb=0.3, panic=1.5, min_body=0.15,
            sl=2.0, tp=4.0, max_bars=25)

Dimensions swept (trail params never explored before):
  trail_act  : [1.5, 2.0, 2.5, 3.0, 3.5]  — ATR multiples before trail activates
  trail_dist : [0.3, 0.4, 0.5, 0.6, 0.8]  — ATR multiples trail trails from best
  tp_mult    : [4.0, 4.5, 5.0, 5.5, 6.0]  — extended TP range
  max_bars   : [18, 22, 25, 30, 0]         — refined MB exit range

Total: 5×5×5×5 = 625 combos
"""

import subprocess, sys
for pkg in ["yfinance", "pandas", "numpy", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
import warnings
import time
warnings.filterwarnings("ignore")

# ── Fixed Stage-1 + Stage-2 winner params ─────────────────────────────────────
TICKER           = "BTCUSD"
PERIOD           = "60d"
ADX_THRESH       = 20
VOL_MULT         = 0.7
SESSION_END_ET   = 14
ADX_SLOPE_BARS   = 0       # off
DI_SPREAD_MIN    = 0.0     # off
PB_PCT           = 0.30
EMA_FAST         = 21
EMA_MID          = 50
EMA_SLOW         = 200
ADX_LEN          = 14
RSI_LEN          = 14
ATR_LEN          = 14
VOL_LEN          = 20
ATR_BL_LEN       = 60
ATR_FLOOR        = 0.0015
RSI_LO_S         = 32.0
RSI_HI_S         = 58.0
SESSION_START_ET = 9
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1
MOMENTUM_BARS    = 5
INITIAL_CAPITAL  = 10_000.0
COMMISSION_PCT   = 0.0006
RISK_PCT         = 0.01

# Fixed Stage-2 winner params (not swept this stage)
PANIC_MULT       = 1.5
MIN_BODY         = 0.15
SL_MULT          = 2.0

# ── Sweep grid ─────────────────────────────────────────────────────────────────
P = {
    "trail_act":  [1.5, 2.0, 2.5, 3.0, 3.5],   # current=2.5
    "trail_dist": [0.3, 0.4, 0.5, 0.6, 0.8],   # current=0.6
    "tp_mult":    [4.0, 4.5, 5.0, 5.5, 6.0],   # current=4.0
    "max_bars":   [18,  22,  25,  30,  0],      # current=25
}

# ── Data download ──────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} 5m (period='{PERIOD}') → resampling to 10m ...")
raw = yf.download(TICKER, period=PERIOD, interval="5m", auto_adjust=True, progress=False)
if raw.empty:
    raise SystemExit(f"No data returned for {TICKER} 5m.")
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)
raw = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
raw = raw[raw["Volume"] > 0].dropna()

_ET = pytz.timezone("America/New_York")
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw.index = raw.index.tz_convert(_ET)

df = raw.resample("10min", label="left", closed="left", origin="start_day").agg(
    {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
).dropna()
df = df[df["Volume"] > 0].copy()
print(f"10m bars: {len(df)}  |  {df.index[0]} → {df.index[-1]}")

# ── Indicators ─────────────────────────────────────────────────────────────────
df["EMA_F"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_M"] = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_S"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta   = df["Close"].diff()
avg_g   = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l   = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up_mv  = df["High"] - df["High"].shift(1)
dn_mv  = df["Low"].shift(1) - df["Low"]
pdm    = np.where((up_mv > dn_mv) & (up_mv > 0), up_mv, 0.0)
ndm    = np.where((dn_mv > up_mv) & (dn_mv > 0), dn_mv, 0.0)
sp     = pd.Series(pdm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
sm     = pd.Series(ndm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * sp / df["ATR"].replace(0, 1e-10)
df["DI_MINUS"] = 100 * sm / df["ATR"].replace(0, 1e-10)
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
    (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["ET_HOUR"] = df.index.hour
df.dropna(inplace=True)

# ── Pre-compute fixed signal components ───────────────────────────────────────
tol        = PB_PCT / 100.0
pb_tol_dn  = df["EMA_F"].shift(1) * (1.0 - tol)
is_trending = (df["ADX"] > ADX_THRESH).values
ema_bear    = ((df["EMA_F"] < df["EMA_M"]) & (df["EMA_M"] < df["EMA_S"])).values
short_pb    = (df["High"].shift(1) >= pb_tol_dn).values
short_rec   = ((df["Close"] < df["EMA_F"]) & (df["Close"] < df["Open"])).values
rsi_fall    = (df["RSI"] < df["RSI"].shift(1)).values
rsi_ok_s    = ((df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)).values
vol_ok      = (df["Volume"] >= df["VOL_MA"] * VOL_MULT).values
atr_fl_ok   = (df["ATR"] / df["Close"] >= ATR_FLOOR).values
di_ok_s     = ((df["DI_MINUS"] - df["DI_PLUS"]) >= DI_SPREAD_MIN).values
session_ok  = ((df["ET_HOUR"] >= SESSION_START_ET) & (df["ET_HOUR"] < SESSION_END_ET)).values
mom_ok_s    = (df["Close"] < df["Close"].shift(MOMENTUM_BARS)).values
# EMA slope disabled (matches backtest EMA_SLOPE_BARS=0)
ema_sl_dn   = np.ones(len(df), dtype=bool)
adx_rising  = np.ones(len(df), dtype=bool)

H   = df["High"].values
L_  = df["Low"].values
C   = df["Close"].values
ATR = df["ATR"].values
ATR_BL = df["ATR_BL"].values
N   = len(df)

body_arr   = ((df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, 1e-10)).values
# Fixed filters: body=0.15, panic=1.5
body_ok    = body_arr >= MIN_BODY
not_panic  = (ATR <= ATR_BL * PANIC_MULT)

base_sig = (short_pb & short_rec & ema_bear & ema_sl_dn & rsi_fall &
            rsi_ok_s & vol_ok & is_trending & adx_rising & di_ok_s &
            session_ok & mom_ok_s & atr_fl_ok & body_ok & not_panic)

print(f"Base signal fires: {base_sig.sum()} times across {N} bars")

# ── Simulation function ────────────────────────────────────────────────────────
def sim(tp_m, sl_m, ta, td, max_b):
    equity = INITIAL_CAPITAL
    pos    = None
    trades_pnl = []
    eq_list    = []
    consec_losses = 0
    cooldown_bars = 0

    for i in range(N):
        atr_i = ATR[i]
        if np.isnan(atr_i) or atr_i == 0:
            eq_list.append(equity)
            continue

        if pos is not None:
            # update best (lowest low for short)
            if L_[i] < pos["best"]:
                pos["best"] = L_[i]
            # trailing stop: activates when price moves ta×ATR in our favour
            trail_px = pos["entry"] - atr_i * ta
            if pos["best"] <= trail_px:
                new_sl = pos["best"] + pos["trail_dist"]
                if new_sl < pos["sl"]:
                    pos["sl"] = new_sl

            # max bars exit (checked BEFORE TP/SL to mirror backtest order)
            if max_b > 0 and pos["bars"] >= max_b:
                xp  = C[i]
                dp  = (pos["entry"] - xp) / pos["entry"] * pos["notional"] \
                      - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                trades_pnl.append(dp)
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                pos = None
                eq_list.append(equity); continue
            pos["bars"] += 1

            htp = L_[i] <= pos["tp"]
            hsl = H[i]  >= pos["sl"]
            if htp or hsl:
                xp  = pos["tp"] if htp else pos["sl"]
                dp  = (pos["entry"] - xp) / pos["entry"] * pos["notional"] \
                      - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                trades_pnl.append(dp)
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                pos = None

        if pos is None:
            if cooldown_bars > 0:
                cooldown_bars -= 1
            elif base_sig[i]:
                sd   = atr_i * sl_m
                notl = min(equity * RISK_PCT / sd * C[i], equity * 5.0)
                pos  = {
                    "entry":      C[i],
                    "sl":         C[i] + sd,
                    "tp":         C[i] - atr_i * tp_m,
                    "best":       C[i],
                    "notional":   notl,
                    "trail_dist": atr_i * td,
                    "bars":       0,
                }

        eq_list.append(equity)

    if not trades_pnl:
        return {"trades": 0, "wr": 0, "pf": 0, "net_pct": 0,
                "final_eq": INITIAL_CAPITAL, "max_dd": 0, "calmar": 0}

    arr    = np.array(trades_pnl)
    wins   = arr[arr > 0]; losses = arr[arr <= 0]
    total  = len(arr); wr = len(wins) / total * 100
    net    = arr.sum(); net_pct = net / INITIAL_CAPITAL * 100
    gp     = wins.sum() if len(wins) > 0 else 0
    gl     = abs(losses.sum()) if len(losses) > 0 else 0
    pf     = gp / gl if gl > 0 else float("inf")
    eq_a   = np.array(eq_list)
    rm     = np.maximum.accumulate(eq_a)
    dd     = ((eq_a - rm) / rm * 100).min()
    calmar = net_pct / abs(dd) if dd < 0 else float("inf")

    return {"trades": total, "wr": round(wr, 1), "pf": round(pf, 3),
            "net_pct": round(net_pct, 2), "final_eq": round(INITIAL_CAPITAL + net, 2),
            "max_dd": round(dd, 2), "calmar": round(calmar, 3)}

# ── Run sweep ──────────────────────────────────────────────────────────────────
from itertools import product

grid = list(product(P["trail_act"], P["trail_dist"], P["tp_mult"], P["max_bars"]))
total_combos = len(grid)
print(f"\nSweeping {total_combos} combos (trail_act × trail_dist × tp × max_bars) …")

results = []
t0 = time.time()

for ta, td, tp, mxb in grid:
    r = sim(tp, SL_MULT, ta, td, mxb)
    results.append({
        "trail_act": ta, "trail_dist": td, "tp_mult": tp, "max_bars": mxb,
        **r
    })

elapsed = time.time() - t0
print(f"Done in {elapsed:.1f}s  ({total_combos} combos)")

# ── Save & report ──────────────────────────────────────────────────────────────
rdf = pd.DataFrame(results)
rdf.to_csv("sweep_stage3_results.csv", index=False)
print(f"Saved → sweep_stage3_results.csv")

# Baseline (current Stage-2 winner params in the grid)
base = rdf[(rdf["trail_act"] == 2.5) & (rdf["trail_dist"] == 0.6) &
           (rdf["tp_mult"] == 4.0) & (rdf["max_bars"] == 25)]
if not base.empty:
    b = base.iloc[0]
    print(f"\nBaseline (Stage-2 winner): {b['trades']}T | WR={b['wr']}% | "
          f"PF={b['pf']} | net={b['net_pct']:+.2f}% | DD={b['max_dd']:.2f}% | "
          f"Calmar={b['calmar']}")

MIN_TRADES = 8

print(f"\n── Top 10 by Calmar (≥{MIN_TRADES} trades) ──────────────────────────────")
top = rdf[rdf["trades"] >= MIN_TRADES].sort_values("calmar", ascending=False).head(10)
print(top[["trail_act","trail_dist","tp_mult","max_bars",
           "trades","wr","pf","net_pct","max_dd","calmar"]].to_string(index=False))

print(f"\n── Top 10 by net% (≥{MIN_TRADES} trades) ──────────────────────────────")
top2 = rdf[rdf["trades"] >= MIN_TRADES].sort_values("net_pct", ascending=False).head(10)
print(top2[["trail_act","trail_dist","tp_mult","max_bars",
            "trades","wr","pf","net_pct","max_dd","calmar"]].to_string(index=False))

print(f"\n── Top 10 by PF (≥{MIN_TRADES} trades) ────────────────────────────────")
top3 = rdf[rdf["trades"] >= MIN_TRADES].sort_values("pf", ascending=False).head(10)
print(top3[["trail_act","trail_dist","tp_mult","max_bars",
            "trades","wr","pf","net_pct","max_dd","calmar"]].to_string(index=False))
