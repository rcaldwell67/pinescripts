"""Stage-4 sweep — two new dimensions:
  1. be_trig  : breakeven stop (move SL to entry once max_runup >= ATR × be_trig)
  2. em_slope : EMA_MID(34) must be rising over last N bars at entry (0=off)

Base (v4.2): AT=20, PB=0.30, TP=3.0, SL=1.5, MaxB=25, RSI:42-75, MB=0.20
→ PF=2.596 | net=+21.80% | WR=63.3% | 30T | MaxDD=-3.60% | Calmar=6.046

Analysis of 11 losses:
  max_runup/ATR ranges 0.33–1.56; all wins ≥ 1.89 → clean gap
  → be_trig=1.2 converts 2 losses (2005 1.36×, 2019-04 1.56×) to ~breakeven
  EMA_MID slope: 2016 summer + 2019 chop may have flat/falling EMA_MID
  DI spread: BAD filter — 13/19 wins have DI- ≥ DI+ (pullback strategy)
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
    tr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
def adxs(h, l, c, n=14):
    up=h.diff(); dn=-l.diff()
    pdm=up.where((up>dn)&(up>0),0.0); ndm=dn.where((dn>up)&(dn>0),0.0)
    tr14=atrs(h,l,c,n)
    pdi=100*pdm.ewm(alpha=1/n,adjust=False).mean()/tr14.replace(0,np.nan)
    ndi=100*ndm.ewm(alpha=1/n,adjust=False).mean()/tr14.replace(0,np.nan)
    dx=100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False).mean()

d = df.copy()
d["EF"]  = ema(d["Close"], 21)
d["EM"]  = ema(d["Close"], 34)
d["ES"]  = ema(d["Close"], 200)
d["ATR"] = atrs(d["High"], d["Low"], d["Close"], 14)
d["ABL"] = d["ATR"].rolling(60).mean()
d["ADX"] = adxs(d["High"], d["Low"], d["Close"], 14)
d["RSI"] = rsif(d["Close"], 14)
d["VM"]  = d["Volume"].rolling(20).mean()
d["BD"]  = (d["Close"] - d["Open"]).abs() / d["ATR"].replace(0, np.nan)

# ── Pre-extracted numpy arrays ─────────────────────────────────────────────────
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
IDX  = d.index; N = len(d)
YRS_ = IDX.year.values

# Shifted arrays
EF_s1 = np.empty(N); EF_s1[0] = np.nan; EF_s1[1:] = EF[:-1]
L_s1  = np.empty(N); L_s1[0]  = np.nan; L_s1[1:]  = L[:-1]

# Fixed base entry signal (AT=20, PB=0.30, VO=1.0, MB=0.20, RL=42, RH=75)
IP_    = AV > ABL * 2.0
TREND_ = (C > ES) & (EF > EM)
pb_u   = EF_s1 * (1.0 + 0.30 / 100.0)
LP_    = (L_s1 <= pb_u) & (C > EF) & (C > O) & (BD_ >= 0.20)
LE_BASE = LP_ & TREND_ & (ADX_ > 20.0) & (RSI_ >= 42.0) & (RSI_ <= 75.0) & (VOL >= VM_ * 1.0) & ~IP_

# Pre-compute EMA_MID slope boolean arrays (EM rising over N bars)
EM_s3 = np.zeros(N, dtype=bool); EM_s3[3:]  = EM[3:]  > EM[:-3]
EM_s5 = np.zeros(N, dtype=bool); EM_s5[5:]  = EM[5:]  > EM[:-5]
EM_s8 = np.zeros(N, dtype=bool); EM_s8[8:]  = EM[8:]  > EM[:-8]
SLOPE_ARRAYS = {0: None, 3: EM_s3, 5: EM_s5, 8: EM_s8}

print(f"Base entry signals: {LE_BASE.sum()} bars")


def sim(LE, SL, TP, MaxB, BE_TRIG):
    eq = INIT_CAP; in_trade = False
    ep = sl = tp_v = q = 0.0; bct = 0; be_active = False; runup_max_val = 0.0
    T = []; ec = [eq]; yrs = {}

    for i in range(N):
        ca = AV[i]
        if ca != ca or ca == 0.0:
            ec.append(eq); continue
        if in_trade:
            bct += 1
            # Track max runup from entry
            cur_runup = H[i] - ep
            if cur_runup > runup_max_val:
                runup_max_val = cur_runup
            # Activate breakeven stop once runup ≥ BE_TRIG × ATR
            if BE_TRIG > 0 and not be_active and runup_max_val >= ca * BE_TRIG:
                be_active = True
                sl = max(sl, ep)       # move SL up to entry (breakeven)
            hit_sl = L[i] <= sl
            hit_tp = H[i] >= tp_v
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
        if not in_trade and LE[i]:
            sd = AV[i] * SL; ep = C[i]; sl = ep - sd; tp_v = ep + AV[i] * TP
            q = eq * RISK_PCT / sd; in_trade = True; bct = 0
            be_active = False; runup_max_val = 0.0
        ec.append(eq)
    if len(T) < MIN_TRADES:
        return None
    arr = np.array(T); w = arr[arr > 0]; lw = arr[arr <= 0]
    gp = w.sum() if len(w) else 0.0; gl = abs(lw.sum()) if len(lw) else 0.0
    pf = gp / gl if gl > 0 else 999.0
    wr = len(w) / len(arr) * 100
    net = arr.sum() / INIT_CAP * 100
    ea2 = np.array(ec); rm = np.maximum.accumulate(ea2)
    dd = ((ea2 - rm) / rm * 100).min()
    calmar = net / abs(dd) if dd != 0 else 0.0
    return {"pf": pf, "wr": wr, "np": net, "n": len(arr), "dd": dd, "calmar": calmar, "yrs": yrs}


# Grid: 5 × 4 × 3 × 3 × 4 = 720 combos — fast
P = {
    "be_trig":   [0, 0.8, 1.0, 1.2, 1.5],    # breakeven stop (×ATR), 0=off
    "em_slope":  [0, 3, 5, 8],                 # EMA_MID must have risen over N bars (0=off)
    "sl":        [1.2, 1.5, 2.0],              # SL mult
    "tp":        [2.5, 3.0, 3.5],              # TP mult
    "maxb":      [0, 20, 25, 30],              # max bars in trade
}
ks = list(P.keys()); total = 1
for v in P.values(): total *= len(v)
print(f"\nSweeping {total:,} combos...", flush=True)

res = []; n = 0
for combo in product(*[P[k] for k in ks]):
    n += 1
    p = dict(zip(ks, combo))
    # Build entry signal array for this slope value
    slope_arr = SLOPE_ARRAYS[p["em_slope"]]
    le = LE_BASE & slope_arr if slope_arr is not None else LE_BASE
    r = sim(LE=le, SL=p["sl"], TP=p["tp"], MaxB=p["maxb"], BE_TRIG=p["be_trig"])
    if r:
        res.append({**p, **r})

rdf = pd.DataFrame(res)
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 300)
pd.set_option("display.float_format", "{:.3f}".format)
cols = ["pf", "wr", "np", "n", "dd", "calmar", "be_trig", "em_slope", "tp", "sl", "maxb"]

print(f"\nDone. {n:,} combos | {len(res)} results")

print("\n" + "="*110)
print("  TOP 20 by Calmar  (n>=12, DD>-8%)")
print("="*110)
q = rdf[(rdf["n"]>=12) & (rdf["dd"]>-8)].sort_values("calmar", ascending=False)
print(q[cols].head(20).to_string(index=False))

print("\n" + "="*110)
print("  TOP 20 by net return  (n>=12, PF>1.8, DD>-8%)")
print("="*110)
q2 = rdf[(rdf["n"]>=12) & (rdf["pf"]>1.8) & (rdf["dd"]>-8)].sort_values("np", ascending=False)
print(q2[cols].head(20).to_string(index=False))

print("\n" + "="*110)
print("  TOP 20 by PF  (n>=12, DD>-6%)")
print("="*110)
q3 = rdf[(rdf["n"]>=12) & (rdf["dd"]>-6)].sort_values("pf", ascending=False)
print(q3[cols].head(20).to_string(index=False))

# Show baselines for context
print("\n" + "="*70)
print("  BASELINE (v4.2): be_trig=0, em_slope=0, sl=1.5, tp=3.0, maxb=25")
base = rdf[(rdf["be_trig"]==0) & (rdf["em_slope"]==0) & (rdf["sl"]==1.5) &
           (rdf["tp"]==3.0) & (rdf["maxb"]==25)]
if not base.empty:
    b = base.iloc[0]
    for k in cols: print(f"  {k:<9}: {b[k]:.3f}")

# Best combos summary
print("\n" + "="*70)
for label, sub in [("BEST Calmar", rdf[(rdf["n"]>=12)&(rdf["dd"]>-8)].sort_values("calmar",ascending=False)),
                   ("BEST net",    rdf[(rdf["n"]>=12)&(rdf["pf"]>1.8)&(rdf["dd"]>-8)].sort_values("np",ascending=False)),
                   ("BEST PF",     rdf[(rdf["n"]>=12)&(rdf["dd"]>-6)].sort_values("pf",ascending=False))]:
    if sub.empty: continue
    b = sub.iloc[0]
    print(f"\n  {label}: PF={b['pf']:.3f} | WR={b['wr']:.1f}% | net={b['np']:.2f}% | n={int(b['n'])} | DD={b['dd']:.2f}% | Calmar={b['calmar']:.3f}")
    for k in ["be_trig","em_slope","tp","sl","maxb"]:
        print(f"    {k:<10}: {b[k]}")

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_stage4_results.csv")
rdf.to_csv(out, index=False)
print(f"\nSaved -> {out}")
