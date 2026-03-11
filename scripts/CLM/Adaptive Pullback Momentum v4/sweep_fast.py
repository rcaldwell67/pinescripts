"""Fast focused parameter sweep for APM v4.1 — CLM 1D
Pre-caches indicator sets, sweeps ~663K combos.
"""
import pandas as pd, numpy as np, yfinance as yf, warnings
from itertools import product
warnings.filterwarnings("ignore")

INIT_CAP = 10_000.0; COMMISSION = 0.0006; RISK_PCT = 0.01; MIN_TRADES = 6

raw = yf.download("CLM", period="max", interval="1d", auto_adjust=True, progress=False)
raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
df = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()
df.index = pd.to_datetime(df.index)
print(f"Rows:{len(df)} | {df.index[0].date()} to {df.index[-1].date()}", flush=True)

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

print("Building indicator caches...", flush=True)
caches = {}
for em in [21, 34, 50, 89]:
    d = df.copy()
    d["EF"] = ema(d["Close"], 21); d["EM"] = ema(d["Close"], em); d["ES"] = ema(d["Close"], 200)
    d["ATR"] = atrs(d["High"], d["Low"], d["Close"], 14); d["ABL"] = d["ATR"].rolling(60).mean()
    d["ADX"] = adxs(d["High"], d["Low"], d["Close"], 14); d["RSI"] = rsif(d["Close"], 14)
    d["VM"] = d["Volume"].rolling(20).mean()
    d["BD"] = (d["Close"] - d["Open"]).abs() / d["ATR"].replace(0, np.nan)
    caches[em] = d
    print(f"  EMA_MID={em}", flush=True)


def sim(D, AT, PB, VO, MB, PM, SL, TP, TA, TD, RL, RH, RS, RX, DL, DS):
    pb_u = D["EF"].shift(1) * (1 + PB / 100)
    pb_d = D["EF"].shift(1) * (1 - PB / 100)
    lp = (D["Low"].shift(1) <= pb_u) & (D["Close"] > D["EF"]) & (D["Close"] > D["Open"]) & (D["BD"] >= MB)
    sp = (D["High"].shift(1) >= pb_d) & (D["Close"] < D["EF"]) & (D["Close"] < D["Open"]) & (D["BD"] >= MB)
    it = D["ADX"] > AT; ip = D["ATR"] > D["ABL"] * PM
    le = (DL & lp & (D["Close"] > D["ES"]) & (D["EF"] > D["EM"]) &
          (D["RSI"] >= RL) & (D["RSI"] <= RH) & (D["Volume"] >= D["VM"] * VO) & it & ~ip).values
    se = (DS & sp & (D["Close"] < D["ES"]) & (D["EF"] < D["EM"]) &
          (D["RSI"] >= RS) & (D["RSI"] <= RX) & (D["Volume"] >= D["VM"] * VO) & it & ~ip).values
    eq = INIT_CAP; it2 = False; dr = None; ep = sl = tp = bp = ea = q = 0.0
    T = []; ec = [INIT_CAP]
    o = D["Open"].values; h = D["High"].values; lw = D["Low"].values
    c = D["Close"].values; av = D["ATR"].values
    for i in range(len(D)):
        ca = av[i]
        if not (ca == ca) or ca == 0:
            ec.append(eq); continue
        if it2:
            if dr == "L":
                if h[i] > bp: bp = h[i]
                if bp >= ep + ea * TA:
                    t = bp - ea * TD
                    if t > sl: sl = t
                if lw[i] <= sl:
                    xp = min(o[i], sl); net = (xp - ep) * q - (ep + xp) * q * COMMISSION
                    eq += net; T.append(net); it2 = False
                elif h[i] >= tp:
                    xp = max(o[i], tp); net = (xp - ep) * q - (ep + xp) * q * COMMISSION
                    eq += net; T.append(net); it2 = False
            else:
                if lw[i] < bp: bp = lw[i]
                if bp <= ep - ea * TA:
                    t = bp + ea * TD
                    if t < sl: sl = t
                if h[i] >= sl:
                    xp = max(o[i], sl); net = (ep - xp) * q - (ep + xp) * q * COMMISSION
                    eq += net; T.append(net); it2 = False
                elif lw[i] <= tp:
                    xp = min(o[i], tp); net = (ep - xp) * q - (ep + xp) * q * COMMISSION
                    eq += net; T.append(net); it2 = False
        if not it2:
            if le[i]:
                sd = ca * SL; ep = c[i]; sl = ep - sd; tp = ep + ca * TP
                ea = ca; bp = ep; q = eq * RISK_PCT / sd; dr = "L"; it2 = True
            elif se[i]:
                sd = ca * SL; ep = c[i]; sl = ep + sd; tp = ep - ca * TP
                ea = ca; bp = ep; q = eq * RISK_PCT / sd; dr = "S"; it2 = True
        ec.append(eq)
    if len(T) < MIN_TRADES: return None
    arr = np.array(T); w = arr[arr > 0]; l = arr[arr <= 0]
    gp = w.sum() if len(w) else 0; gl = abs(l.sum()) if len(l) else 0
    pf = gp / gl if gl > 0 else 999
    wr = len(w) / len(arr) * 100
    np2 = (eq - INIT_CAP) / INIT_CAP * 100
    ea2 = np.array(ec); rm = np.maximum.accumulate(ea2)
    dd = ((ea2 - rm) / rm * 100).min()
    return {"pf": pf, "wr": wr, "np": np2, "n": len(arr), "dd": dd}


# ~576 focused combos  (runs in ~5-10 s with Python bar-by-bar loop)
P = {
    "em":  [21, 34, 50],          # 3
    "at":  [20, 25, 28, 33],      # 4
    "pb":  [0.10, 0.15, 0.25],    # 3
    "mb":  [0.15],                # 1
    "pm":  [2.0],                 # 1
    "sl":  [1.0, 1.5, 2.0],       # 3
    "tp":  [1.5, 2.0, 2.5, 3.0],  # 4
    "ta":  [2.0, 99.0],           # 2
    "td":  [0.5],                 # 1
    "rl":  [42],  "rh": [70],     # 1
    "rs":  [30],  "rx": [58],     # 1
    "vm":  [1.0],                 # 1
    "dl":  [True],                # 1
    "ds":  [True, False],         # 2
    # 3*4*3*3*4*2*2 = 1728 combos
}
ks = list(P.keys())
total = 1
for v in P.values(): total *= len(v)
print(f"\nSweeping {total:,} combos...", flush=True)

res = []; n = 0
for combo in product(*[P[k] for k in ks]):
    n += 1
    if n % 100_000 == 0:
        print(f"  {n:>8,}/{total:,}  hits={len(res)}", flush=True)
    p = dict(zip(ks, combo))
    r = sim(caches[p["em"]], p["at"], p["pb"], p["vm"], p["mb"], p["pm"],
            p["sl"], p["tp"], p["ta"], p["td"],
            p["rl"], p["rh"], p["rs"], p["rx"], p["dl"], p["ds"])
    if r and r["pf"] > 1.2 and r["np"] > 1.0 and r["dd"] > -15.0:
        res.append({**p, **r})

print(f"\nDone. {n:,} combos. {len(res)} hits (PF>1.2, net>1%, DD>-15%).", flush=True)

if not res:
    print("Relaxing to PF>1.0, net>0...", flush=True)
    res = []
    for combo in product(*[P[k] for k in ks]):
        p = dict(zip(ks, combo))
        r = sim(caches[p["em"]], p["at"], p["pb"], p["vm"], p["mb"], p["pm"],
                p["sl"], p["tp"], p["ta"], p["td"],
                p["rl"], p["rh"], p["rs"], p["rx"], p["dl"], p["ds"])
        if r and r["pf"] > 1.0 and r["np"] > 0:
            res.append({**p, **r})
    print(f"  Relaxed: {len(res)} hits.", flush=True)

if res:
    rdf = pd.DataFrame(res).sort_values("pf", ascending=False)
    cols = ["pf", "wr", "np", "n", "dd", "at", "pb", "tp", "sl", "ta",
            "mb", "pm", "em", "rl", "rh", "rs", "rx", "vm", "dl", "ds"]
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 260)
    pd.set_option("display.float_format", "{:.3f}".format)
    print(f"\n{'='*110}\n  TOP 30 by Profit Factor\n{'='*110}")
    print(rdf[cols].head(30).to_string(index=False))
    best = rdf.iloc[0]
    print(f"\n{'='*60}\n  BEST COMBO\n{'='*60}")
    for k in cols:
        print(f"  {k:<6}: {best[k]}")
    import os
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_apm_v4_1d_results.csv")
    rdf.to_csv(out, index=False)
    print(f"\nSaved -> {out}")
else:
    print("NO profitable combos found — CLM 1D may need fundamentally different approach.")
