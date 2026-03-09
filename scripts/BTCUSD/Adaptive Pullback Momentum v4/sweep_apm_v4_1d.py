"""
Multi-phase improvement sweep — APM v4.0 @ 1D BTC-USD
Builds on each phase's best result sequentially.
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

# ── Download once ──────────────────────────────────────────────────────────────
print("Downloading BTC-USD 1d max …")
raw = yf.download("BTC-USD", period="max", interval="1d",
                  auto_adjust=True, progress=False)
raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
df_raw = raw[["Open","High","Low","Close","Volume"]].copy().dropna()
df_raw.index = pd.to_datetime(df_raw.index)
print(f"  Rows: {len(df_raw)}  {df_raw.index[0].date()} → {df_raw.index[-1].date()}\n")

INIT_CAP   = 10_000.0
COMM       = 0.0006
RISK       = 0.01

# ── Pre-compute all indicators once ───────────────────────────────────────────
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff()
    u = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    v = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + u / v.replace(0, np.nan))
def atr_s(h, l, c, n=14):
    tr = pd.concat([h-l,(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
def adx_s(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = up.where((up>dn)&(up>0), 0.0)
    ndm = dn.where((dn>up)&(dn>0), 0.0)
    tr14 = atr_s(h, l, c, n)
    pdi = 100*pdm.ewm(alpha=1/n,adjust=False).mean()/tr14.replace(0,np.nan)
    ndi = 100*ndm.ewm(alpha=1/n,adjust=False).mean()/tr14.replace(0,np.nan)
    dx  = 100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()

df = df_raw.copy()
df["EMA_F"]       = ema(df["Close"], 21)
df["EMA_M"]       = ema(df["Close"], 50)
df["EMA_S"]       = ema(df["Close"], 200)
df["ATR"]         = atr_s(df["High"], df["Low"], df["Close"], 14)
df["ATR_BL"]      = df["ATR"].rolling(60).mean()
df["ADX"]         = adx_s(df["High"], df["Low"], df["Close"], 14)
df["RSI"]         = rsi(df["Close"], 14)
df["VOL_MA"]      = df["Volume"].rolling(20).mean()
df["BODY"]        = (df["Close"]-df["Open"]).abs() / df["ATR"].replace(0, np.nan)
df["EMA_F_SLOPE"] = df["EMA_F"] - df["EMA_F"].shift(3)
df["RSI_SLOPE"]   = df["RSI"] - df["RSI"].shift(1)
df = df.dropna()

# ── Core backtest engine ───────────────────────────────────────────────────────
def backtest(cfg):
    ADX   = cfg.get("adx",    25.0)
    PB    = cfg.get("pb_pct", 0.15)
    VM    = cfg.get("vol_mult",1.0)
    MB    = cfg.get("min_body",0.15)
    PM    = cfg.get("panic",   1.5)
    SL    = cfg.get("sl",      1.5)
    TP    = cfg.get("tp",      2.0)
    TA    = cfg.get("trail_act",1.5)
    TD    = cfg.get("trail_dist",0.8)
    AF    = cfg.get("atr_floor",0.0)
    LO_L  = cfg.get("rsi_lo_l", 42.0); HI_L = cfg.get("rsi_hi_l", 68.0)
    LO_S  = cfg.get("rsi_lo_s", 32.0); HI_S = cfg.get("rsi_hi_s", 58.0)
    SLOPE = cfg.get("ema_slope", False)
    RDIR  = cfg.get("rsi_dir",   False)
    LONGS = cfg.get("longs",  True)
    SHRTS = cfg.get("shorts", True)

    d = df.copy()
    pb_up   = d["EMA_F"].shift(1) * (1 + PB/100)
    pb_dn   = d["EMA_F"].shift(1) * (1 - PB/100)
    long_pb  = (d["Low"].shift(1)  <= pb_up) & (d["Close"] > d["EMA_F"]) & \
               (d["Close"] > d["Open"]) & (d["BODY"] >= MB)
    short_pb = (d["High"].shift(1) >= pb_dn) & (d["Close"] < d["EMA_F"]) & \
               (d["Close"] < d["Open"]) & (d["BODY"] >= MB)

    is_t  = d["ADX"] > ADX
    is_p  = d["ATR"] > d["ATR_BL"] * PM
    sl_ok = (d["EMA_F_SLOPE"] > 0)  if SLOPE else pd.Series(True, index=d.index)
    ss_ok = (d["EMA_F_SLOPE"] < 0)  if SLOPE else pd.Series(True, index=d.index)
    ru    = (d["RSI_SLOPE"] > 0)    if RDIR  else pd.Series(True, index=d.index)
    rd    = (d["RSI_SLOPE"] < 0)    if RDIR  else pd.Series(True, index=d.index)

    long_sig  = (LONGS & long_pb  & (d["Close"] > d["EMA_S"]) & (d["EMA_F"] > d["EMA_M"]) &
                 (d["RSI"] >= LO_L) & (d["RSI"] <= HI_L) &
                 (d["Volume"] >= d["VOL_MA"] * VM) & is_t & ~is_p & sl_ok & ru)
    short_sig = (SHRTS & short_pb & (d["Close"] < d["EMA_S"]) & (d["EMA_F"] < d["EMA_M"]) &
                 (d["RSI"] >= LO_S) & (d["RSI"] <= HI_S) &
                 (d["Volume"] >= d["VOL_MA"] * VM) & is_t & ~is_p & ss_ok & rd)

    o = d["Open"].values; h = d["High"].values
    l_ = d["Low"].values; c = d["Close"].values
    atr_v = d["ATR"].values; idx = d.index
    ls = long_sig.values; ss = short_sig.values

    eq = INIT_CAP; in_t = False; direct = None
    ep = sl_p = tp_p = bp = ea = qty = 0.0; et = None
    trades = []

    for i in range(len(d)):
        ca = atr_v[i]
        if np.isnan(ca) or ca == 0: continue
        eff = max(ca, c[i] * AF); exited = False

        if in_t:
            if direct == "long":
                if h[i] > bp: bp = h[i]
                if bp >= ep + ea*TA:
                    t = bp - ea*TD
                    if t > sl_p: sl_p = t
                if l_[i] <= sl_p:
                    xp = min(o[i], sl_p); pnl = (xp-ep)*qty
                    eq += pnl - (ep+xp)*qty*COMM
                    trades.append({"dir":"long","pnl":pnl-(ep+xp)*qty*COMM,
                                   "eq":eq,"why":"SL/TR","et":et,"xt":idx[i]})
                    in_t = False; exited = True
                elif h[i] >= tp_p:
                    xp = max(o[i], tp_p); pnl = (xp-ep)*qty
                    eq += pnl - (ep+xp)*qty*COMM
                    trades.append({"dir":"long","pnl":pnl-(ep+xp)*qty*COMM,
                                   "eq":eq,"why":"TP","et":et,"xt":idx[i]})
                    in_t = False; exited = True
            else:
                if l_[i] < bp: bp = l_[i]
                if bp <= ep - ea*TA:
                    t = bp + ea*TD
                    if t < sl_p: sl_p = t
                if h[i] >= sl_p:
                    xp = max(o[i], sl_p); pnl = (ep-xp)*qty
                    eq += pnl - (ep+xp)*qty*COMM
                    trades.append({"dir":"short","pnl":pnl-(ep+xp)*qty*COMM,
                                   "eq":eq,"why":"SL/TR","et":et,"xt":idx[i]})
                    in_t = False; exited = True
                elif l_[i] <= tp_p:
                    xp = min(o[i], tp_p); pnl = (ep-xp)*qty
                    eq += pnl - (ep+xp)*qty*COMM
                    trades.append({"dir":"short","pnl":pnl-(ep+xp)*qty*COMM,
                                   "eq":eq,"why":"TP","et":et,"xt":idx[i]})
                    in_t = False; exited = True

        if not in_t:
            if ls[i]:
                sd = eff*SL; ep=c[i]; sl_p=ep-sd; tp_p=ep+eff*TP
                ea=eff; bp=ep; qty=eq*RISK/sd; et=idx[i]
                direct="long"; in_t=True
            elif ss[i]:
                sd = eff*SL; ep=c[i]; sl_p=ep+sd; tp_p=ep-eff*TP
                ea=eff; bp=ep; qty=eq*RISK/sd; et=idx[i]
                direct="short"; in_t=True

    if not trades:
        return {"pct":-999,"pf":0,"wr":0,"n":0,"dd":-100,"nl":0,"ns":0,"wrl":0,"wrs":0}
    t = pd.DataFrame(trades)
    wins = t[t["pnl"]>0]; losses = t[t["pnl"]<=0]
    n = len(t); wr = len(wins)/n*100
    gp = wins["pnl"].sum(); gl = abs(losses["pnl"].sum())
    pf = gp/gl if gl>0 else 999
    pct = (eq-INIT_CAP)/INIT_CAP*100
    eq_a = t["eq"].values
    rm = np.maximum.accumulate(np.concatenate([[INIT_CAP], eq_a]))
    dd = ((np.concatenate([[INIT_CAP], eq_a])-rm)/rm*100).min()
    nl = len(t[t["dir"]=="long"]); ns = len(t[t["dir"]=="short"])
    wrl = (t[t["dir"]=="long"]["pnl"]>0).mean()*100 if nl>0 else 0
    wrs = (t[t["dir"]=="short"]["pnl"]>0).mean()*100 if ns>0 else 0
    return {"pct":pct,"pf":pf,"wr":wr,"n":n,"dd":dd,"nl":nl,"ns":ns,"wrl":wrl,"wrs":wrs}

def hdr(s): print(f"\n{'─'*62}\n  {s}\n{'─'*62}")
def row(tag, r):
    print(f"  {tag:<36} n={r['n']:3d}  WR={r['wr']:5.1f}%  "
          f"PF={r['pf']:.3f}  {r['pct']:+.2f}%  DD={r['dd']:.1f}%")

# ── PHASE 1: ATR floor ─────────────────────────────────────────────────────────
hdr("PHASE 1 — ATR floor")
base = {"adx":25,"sl":1.5,"tp":2.0,"trail_act":1.5,"trail_dist":0.8,
        "vol_mult":1.0,"min_body":0.15,"panic":1.5,"pb_pct":0.15,
        "ema_slope":False,"rsi_dir":False,"longs":True,"shorts":True,"atr_floor":0.0}
p1_best = None
for fl in [0.0, 0.0010, 0.0015, 0.0020, 0.0025, 0.0030]:
    cfg = {**base, "atr_floor": fl}; r = backtest(cfg)
    row(f"ATR floor {fl*100:.2f}%", r)
    if p1_best is None or r["pct"] > p1_best[1]["pct"]: p1_best = (cfg, r)
print(f"\n  ★ ATR floor {p1_best[0]['atr_floor']*100:.2f}% → {p1_best[1]['pct']:+.2f}%")

# ── PHASE 2: EMA slope + RSI direction ────────────────────────────────────────
hdr("PHASE 2 — EMA slope & RSI direction")
p2b = {**p1_best[0]}
p2_best = None
for slope, rdir in [(False,False),(True,False),(False,True),(True,True)]:
    cfg = {**p2b,"ema_slope":slope,"rsi_dir":rdir}; r = backtest(cfg)
    tag = ("slope+rsi_dir" if slope and rdir else
           "slope only" if slope else "rsi_dir only" if rdir else "neither")
    row(tag, r)
    if p2_best is None or r["pct"] > p2_best[1]["pct"]: p2_best = (cfg, r)
print(f"\n  ★ slope={p2_best[0]['ema_slope']} rsi_dir={p2_best[0]['rsi_dir']} → {p2_best[1]['pct']:+.2f}%")

# ── PHASE 3: TP × SL ──────────────────────────────────────────────────────────
hdr("PHASE 3 — TP × SL sweep")
p3b = {**p2_best[0]}
p3_best = None
for sl in [1.0, 1.5, 2.0, 2.5, 3.0]:
    for tp in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        cfg = {**p3b,"sl":sl,"tp":tp}; r = backtest(cfg)
        row(f"SL×{sl}  TP×{tp}", r)
        if p3_best is None or r["pct"] > p3_best[1]["pct"]: p3_best = (cfg, r)
print(f"\n  ★ SL×{p3_best[0]['sl']} TP×{p3_best[0]['tp']} → {p3_best[1]['pct']:+.2f}%")

# ── PHASE 4: ADX threshold ────────────────────────────────────────────────────
hdr("PHASE 4 — ADX threshold")
p4b = {**p3_best[0]}
p4_best = None
for adx in [15, 18, 20, 22, 25, 28, 30, 33, 35]:
    cfg = {**p4b,"adx":adx}; r = backtest(cfg)
    row(f"ADX>{adx}", r)
    if p4_best is None or r["pct"] > p4_best[1]["pct"]: p4_best = (cfg, r)
print(f"\n  ★ ADX>{p4_best[0]['adx']} → {p4_best[1]['pct']:+.2f}%")

# ── PHASE 5: Trail activate × distance ────────────────────────────────────────
hdr("PHASE 5 — Trail activate × distance")
p5b = {**p4_best[0]}
p5_best = None
for ta in [1.0, 1.5, 2.0, 2.5, 3.0]:
    for td in [0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5]:
        cfg = {**p5b,"trail_act":ta,"trail_dist":td}; r = backtest(cfg)
        row(f"trail act×{ta}  dist×{td}", r)
        if p5_best is None or r["pct"] > p5_best[1]["pct"]: p5_best = (cfg, r)
print(f"\n  ★ trail_act×{p5_best[0]['trail_act']} trail_dist×{p5_best[0]['trail_dist']} → {p5_best[1]['pct']:+.2f}%")

# ── PHASE 6: Volume & body ────────────────────────────────────────────────────
hdr("PHASE 6 — Volume multiplier & min body")
p6b = {**p5_best[0]}
p6_best = None
for vm in [0.8, 1.0, 1.2, 1.5, 2.0]:
    for mb in [0.10, 0.15, 0.20, 0.25, 0.30]:
        cfg = {**p6b,"vol_mult":vm,"min_body":mb}; r = backtest(cfg)
        row(f"vol×{vm}  body×{mb}", r)
        if p6_best is None or r["pct"] > p6_best[1]["pct"]: p6_best = (cfg, r)
print(f"\n  ★ vol×{p6_best[0]['vol_mult']} body×{p6_best[0]['min_body']} → {p6_best[1]['pct']:+.2f}%")

# ── PHASE 7: PB tolerance & panic ────────────────────────────────────────────
hdr("PHASE 7 — PB tolerance & panic multiplier")
p7b = {**p6_best[0]}
p7_best = None
for pb, pm in [(0.10,1.5),(0.15,1.5),(0.20,1.5),(0.25,1.5),(0.30,1.5),
               (0.15,1.3),(0.15,2.0),(0.20,2.0),(0.25,2.0)]:
    cfg = {**p7b,"pb_pct":pb,"panic":pm}; r = backtest(cfg)
    row(f"PB {pb}%  panic×{pm}", r)
    if p7_best is None or r["pct"] > p7_best[1]["pct"]: p7_best = (cfg, r)
print(f"\n  ★ PB {p7_best[0]['pb_pct']}%  panic×{p7_best[0]['panic']} → {p7_best[1]['pct']:+.2f}%")

# ── PHASE 8: Long / short direction ──────────────────────────────────────────
hdr("PHASE 8 — Direction: longs / shorts / both")
p8b = {**p7_best[0]}
p8_best = None
for lg, sh in [(True,True),(True,False),(False,True)]:
    cfg = {**p8b,"longs":lg,"shorts":sh}; r = backtest(cfg)
    tag = "both" if lg and sh else ("longs only" if lg else "shorts only")
    row(tag, r)
    if p8_best is None or r["pct"] > p8_best[1]["pct"]: p8_best = (cfg, r)
print(f"\n  ★ longs={p8_best[0]['longs']} shorts={p8_best[0]['shorts']} → {p8_best[1]['pct']:+.2f}%")

# ── PHASE 9: RSI band fine-tune ───────────────────────────────────────────────
hdr("PHASE 9 — RSI band fine-tune")
p9b = {**p8_best[0]}
p9_best = None
longs_active  = p9b.get("longs", True)
shorts_active = p9b.get("shorts", True)
combos = []
if longs_active:
    combos += [(lo, hi, p9b.get("rsi_lo_s",32), p9b.get("rsi_hi_s",58))
               for lo,hi in [(35,65),(38,68),(42,68),(42,72),(45,68),(45,72),(40,70)]]
if shorts_active and not longs_active:
    combos += [(p9b.get("rsi_lo_l",42), p9b.get("rsi_hi_l",68), lo, hi)
               for lo,hi in [(25,55),(28,55),(30,58),(32,58),(35,60)]]
if not combos:
    combos = [(42,68,32,58)]
for ll,hl,ls_,hs in combos:
    cfg = {**p9b,"rsi_lo_l":ll,"rsi_hi_l":hl,"rsi_lo_s":ls_,"rsi_hi_s":hs}
    r = backtest(cfg)
    row(f"RSI L:{ll}-{hl}  S:{ls_}-{hs}", r)
    if p9_best is None or r["pct"] > p9_best[1]["pct"]: p9_best = (cfg, r)
print(f"\n  ★ RSI L:{p9_best[0]['rsi_lo_l']}-{p9_best[0]['rsi_hi_l']} → {p9_best[1]['pct']:+.2f}%")

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
best_cfg, best_r = p9_best
print(f"\n{'='*62}")
print(f"  OPTIMAL CONFIGURATION  ({best_r['pct']:+.2f}% net, PF={best_r['pf']:.3f})")
print(f"{'='*62}")
for k,v in best_cfg.items():
    print(f"  {k:<18}: {v}")
print(f"  {'─'*40}")
print(f"  Trades     : {best_r['n']}  (L={best_r['nl']}, S={best_r['ns']})")
print(f"  Win rate   : {best_r['wr']:.1f}%  (L={best_r['wrl']:.1f}%, S={best_r['wrs']:.1f}%)")
print(f"  Profit fac : {best_r['pf']:.3f}")
print(f"  Net return : {best_r['pct']:+.2f}%")
print(f"  Max DD     : {best_r['dd']:.2f}%")
print(f"{'='*62}")
