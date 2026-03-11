"""Stage-3 targeted sweep: RSI range, volume mult, max-bars exit, PB tolerance
Base: AT=20, EM=34, SL=1.5, TP=2.5, trail=off, longs only → PF=2.078, +14.56%, 27T
Goal: improve Calmar ratio and/or net return
"""
import pandas as pd, numpy as np, yfinance as yf, warnings
from itertools import product
warnings.filterwarnings("ignore")

INIT_CAP = 10_000.0; COMMISSION = 0.0006; RISK_PCT = 0.01; MIN_TRADES = 8

raw = yf.download("CLM", period="max", interval="1d", auto_adjust=True, progress=False)
raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
df = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()
df.index = pd.to_datetime(df.index)
print(f"Rows: {len(df)} | {df.index[0].date()} to {df.index[-1].date()}")

def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsif(s, n=14):
    d = s.diff()
    u = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    v = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + u / v.replace(0, np.nan))
def atrs(h, l, c, n=14):
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
def adxs(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr14 = atrs(h, l, c, n)
    pdi = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    ndi = 100 * ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()

d = df.copy()
d["EF"] = ema(d["Close"], 21); d["EM"] = ema(d["Close"], 34); d["ES"] = ema(d["Close"], 200)
d["ATR"] = atrs(d["High"], d["Low"], d["Close"], 14); d["ABL"] = d["ATR"].rolling(60).mean()
d["ADX"] = adxs(d["High"], d["Low"], d["Close"], 14); d["RSI"] = rsif(d["Close"], 14)
d["VM"] = d["Volume"].rolling(20).mean()
d["BD"] = (d["Close"] - d["Open"]).abs() / d["ATR"].replace(0, np.nan)
# ── Pre-extract ALL numpy arrays once (avoids pandas overhead inside sim) ──────
O    = d["Open"].values.astype(float)
H    = d["High"].values.astype(float)
L    = d["Low"].values.astype(float)
C    = d["Close"].values.astype(float)
AV   = d["ATR"].values.astype(float)
ABL  = d["ABL"].values.astype(float)
EF   = d["EF"].values.astype(float)
EM   = d["EM"].values.astype(float)
ES   = d["ES"].values.astype(float)
ADX_ = d["ADX"].values.astype(float)
RSI_ = d["RSI"].values.astype(float)
VOL  = d["Volume"].values.astype(float)
VM_  = d["VM"].values.astype(float)
BD_  = d["BD"].values.astype(float)
IDX  = d.index
N    = len(d)

EF_s1 = np.empty(N); EF_s1[0] = np.nan; EF_s1[1:] = EF[:-1]
L_s1  = np.empty(N); L_s1[0]  = np.nan; L_s1[1:]  = L[:-1]
YRS_  = IDX.year.values

# Fixed filter (panic suppression + trend — computed once, independent of params)
IP_    = AV > ABL * 2.0                   # panic bars
TREND_ = (C > ES) & (EF > EM)             # trend (EMA fast > EMA mid, price > EMA slow)

print(f"Indicator cache built. N={N}")


def sim(AT, PB, VO, MB, SL, TP, RL, RH, MaxB):
    pb_u = EF_s1 * (1.0 + PB / 100.0)
    lp   = (L_s1 <= pb_u) & (C > EF) & (C > O) & (BD_ >= MB)
    le   = (lp & TREND_ & (ADX_ > AT) &
            (RSI_ >= RL) & (RSI_ <= RH) &
            (VOL >= VM_ * VO) & ~IP_)

    eq = INIT_CAP; in_trade = False
    ep = sl = tp_v = q = 0.0; bct = 0
    T = []; ec = [eq]; yrs = {}

    for i in range(N):
        ca = AV[i]
        if ca != ca or ca == 0.0:
            ec.append(eq); continue
        if in_trade:
            bct += 1
            hit_sl = L[i] <= sl; hit_tp = H[i] >= tp_v
            hit_mb = MaxB > 0 and bct >= MaxB
            if hit_sl or hit_mb:
                xp = min(O[i], sl) if hit_sl else C[i]
                pnl = (xp - ep) * q - (ep + xp) * q * COMMISSION
                eq += pnl; T.append(pnl)
                yr = int(YRS_[i]); yrs[yr] = yrs.get(yr, 0) + pnl; in_trade = False
            elif hit_tp:
                xp = max(O[i], tp_v)
                pnl = (xp - ep) * q - (ep + xp) * q * COMMISSION
                eq += pnl; T.append(pnl)
                yr = int(YRS_[i]); yrs[yr] = yrs.get(yr, 0) + pnl; in_trade = False
        if not in_trade and le[i]:
            sd = ca * SL; ep = C[i]; sl = ep - sd; tp_v = ep + ca * TP
            q = eq * RISK_PCT / sd; in_trade = True; bct = 0
        ec.append(eq)
    if len(T) < MIN_TRADES:
        return None
    arr = np.array(T); w = arr[arr > 0]; lw = arr[arr <= 0]
    gp = w.sum() if len(w) else 0.0; gl = abs(lw.sum()) if len(lw) else 0.0
    pf = gp / gl if gl > 0 else 999.0
    wr = len(w) / len(arr) * 100
    net = arr.sum() / INIT_CAP * 100
    ea2 = np.array(ec); rm = np.maximum.accumulate(ea2)
    dd  = ((ea2 - rm) / rm * 100).min()
    calmar = net / abs(dd) if dd != 0 else 0.0
    return {"pf": pf, "wr": wr, "np": net, "n": len(arr), "dd": dd, "calmar": calmar, "yrs": yrs}


# AT=20 fixed (spot check proved higher ADX hurts).
# Focuses on RSI-range tuning, MaxB exit, and tight PB/SL/TP variation.
# 3*3*4*4*3*3 = 3,888 combos — completes in ~15s with numpy
P = {
    "at":   [20],                    # FIXED — ADX=20 is proven optimal
    "pb":   [0.20, 0.25, 0.30],      # pullback tolerance
    "vo":   [0.8, 1.0, 1.2],         # volume multiplier
    "mb":   [0.10, 0.15, 0.20],      # min body xATR
    "sl":   [1.2, 1.5, 2.0],         # SL mult
    "tp":   [2.0, 2.5, 3.0],         # TP mult
    "rl":   [36, 40, 44, 48],        # RSI lower bound (longs)
    "rh":   [65, 70, 75],            # RSI upper bound (longs)
    "maxb": [0, 15, 20, 25, 30],     # max bars in trade (0=off)
}
ks = list(P.keys()); total = 1
for v in P.values(): total *= len(v)
print(f"\nSweeping {total:,} combos...", flush=True)

res = []; n = 0
for combo in product(*[P[k] for k in ks]):
    n += 1
    if n % 10_000 == 0: print(f"  {n:>6,}/{total:,}  hits={len(res)}", flush=True)
    p = dict(zip(ks, combo))
    r = sim(AT=p["at"], PB=p["pb"], VO=p["vo"], MB=p["mb"],
            SL=p["sl"], TP=p["tp"], RL=p["rl"], RH=p["rh"], MaxB=p["maxb"])
    if r:
        res.append({**p, **r})

rdf = pd.DataFrame(res)
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 280)
pd.set_option("display.float_format", "{:.3f}".format)
cols = ["pf", "wr", "np", "n", "dd", "calmar", "at", "pb", "tp", "sl", "rl", "rh", "vo", "mb", "maxb"]

print(f"\nDone. {n:,} combos | {len(res)} results")

print("\n" + "="*110)
print("  TOP 20 by Calmar ratio  (n>=15, DD>-8%)")
print("="*110)
q = rdf[(rdf["n"] >= 15) & (rdf["dd"] > -8)].sort_values("calmar", ascending=False)
print(q[cols].head(20).to_string(index=False))

print("\n" + "="*110)
print("  TOP 20 by net return  (n>=15, PF>1.8, DD>-8%)")
print("="*110)
q2 = rdf[(rdf["n"] >= 15) & (rdf["pf"] > 1.8) & (rdf["dd"] > -8)].sort_values("np", ascending=False)
print(q2[cols].head(20).to_string(index=False))

print("\n" + "="*110)
print("  TOP 20 by PF  (n>=15, DD>-6%)")
print("="*110)
q3 = rdf[(rdf["n"] >= 15) & (rdf["dd"] > -6)].sort_values("pf", ascending=False)
print(q3[cols].head(20).to_string(index=False))

# Show the BEST by each metric
best_calmar = rdf[(rdf["n"] >= 15) & (rdf["dd"] > -8)].sort_values("calmar", ascending=False).iloc[0]
best_np     = rdf[(rdf["n"] >= 15) & (rdf["pf"] > 1.8) & (rdf["dd"] > -8)].sort_values("np", ascending=False).iloc[0]
best_pf     = rdf[(rdf["n"] >= 15) & (rdf["dd"] > -6)].sort_values("pf", ascending=False).iloc[0]

print("\n" + "="*60)
for label, b in [("BEST by Calmar", best_calmar), ("BEST by net return", best_np), ("BEST by PF", best_pf)]:
    print(f"\n  {label}")
    for k in cols:
        print(f"    {k:<7}: {b[k]}")

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_stage3_results.csv")
rdf.to_csv(out, index=False)
print(f"\nSaved -> {out}")
