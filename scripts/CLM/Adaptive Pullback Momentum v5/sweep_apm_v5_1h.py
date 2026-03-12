"""
Multi-phase improvement sweep — APM v5 @ 1h CLM (WTI Crude Oil futures)
Builds on each phase's best result to find the optimal parameter set.

CLM baseline (from v1 15m + v2 30m sweep history):
  ADX_THRESH=20, ATR_FLOOR=0.10%, VOL_MULT=0.70, PB_PCT=0.20
  Longs + Shorts enabled, RSI_LO_L=40, RSI_HI_L=70, RSI_LO_S=30, RSI_HI_S=60
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

# ── Download once ──────────────────────────────────────────────────────────────
print("Downloading CLM 1h max …")
raw = yf.download("CLM", period="max", interval="1h",
                  auto_adjust=True, progress=False)
raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
df_raw = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()
df_raw.index = pd.to_datetime(df_raw.index)
print(f"  Rows: {len(df_raw)}  {df_raw.index[0].date()} → {df_raw.index[-1].date()}\n")

INIT_CAP   = 10_000.0
COMMISSION = 0.0006
RISK_PCT   = 0.01

# ── Indicators (computed once on full df) ──────────────────────────────────────
def ema(s, n):  return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff()
    u = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    v = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + u/v.replace(0, np.nan))
def atr_s(h, l, c, n=14):
    tr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
def adx_s(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr14 = atr_s(h, l, c, n)
    pdi = 100*pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    ndi = 100*ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    dx  = 100*(pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()

df = df_raw.copy()
df["EMA_F"]  = ema(df["Close"], 21)
df["EMA_M"]  = ema(df["Close"], 50)
df["EMA_S"]  = ema(df["Close"], 200)
df["ATR"]    = atr_s(df["High"], df["Low"], df["Close"], 14)
df["ATR_BL"] = df["ATR"].rolling(50).mean()
df["ADX"]    = adx_s(df["High"], df["Low"], df["Close"], 14)
df["RSI"]    = rsi(df["Close"], 14)
df["VOL_MA"] = df["Volume"].rolling(20).mean()
df["BODY"]   = (df["Close"]-df["Open"]).abs() / df["ATR"].replace(0, np.nan)
df["EMA_F_SLOPE"] = df["EMA_F"] - df["EMA_F"].shift(3)
df["RSI_SLOPE"]   = df["RSI"]   - df["RSI"].shift(1)
df = df.dropna()

# ── Core backtest engine ───────────────────────────────────────────────────────
def backtest(cfg):
    ADX_THRESH = cfg.get("adx",       20.0)
    PB_PCT     = cfg.get("pb_pct",    0.20)
    VOL_MULT   = cfg.get("vol_mult",  0.70)
    MIN_BODY   = cfg.get("min_body",  0.20)
    PANIC_MULT = cfg.get("panic",     1.5)
    SL_MULT    = cfg.get("sl",        1.5)
    TP_MULT    = cfg.get("tp",        2.0)
    TRAIL_ACT  = cfg.get("trail_act", 2.5)
    TRAIL_DIST = cfg.get("trail_dist",0.5)
    ATR_FLOOR  = cfg.get("atr_floor", 0.0010)
    RSI_LO_L   = cfg.get("rsi_lo_l", 40.0); RSI_HI_L = cfg.get("rsi_hi_l", 70.0)
    RSI_LO_S   = cfg.get("rsi_lo_s", 30.0); RSI_HI_S = cfg.get("rsi_hi_s", 60.0)
    USE_SLOPE  = cfg.get("ema_slope", True)
    USE_RSI_DIR= cfg.get("rsi_dir",   False)
    LONGS      = cfg.get("longs",     True)
    SHORTS     = cfg.get("shorts",    True)

    d = df.copy()
    pb_up = d["EMA_F"].shift(1) * (1 + PB_PCT/100)
    pb_dn = d["EMA_F"].shift(1) * (1 - PB_PCT/100)
    long_pb  = (d["Low"].shift(1)  <= pb_up) & (d["Close"] > d["EMA_F"]) & \
               (d["Close"] > d["Open"]) & (d["BODY"] >= MIN_BODY)
    short_pb = (d["High"].shift(1) >= pb_dn) & (d["Close"] < d["EMA_F"]) & \
               (d["Close"] < d["Open"]) & (d["BODY"] >= MIN_BODY)

    is_trending = d["ADX"] > ADX_THRESH
    is_panic    = d["ATR"] > d["ATR_BL"] * PANIC_MULT

    slope_ok_l = (d["EMA_F_SLOPE"] > 0) if USE_SLOPE   else pd.Series(True, index=d.index)
    slope_ok_s = (d["EMA_F_SLOPE"] < 0) if USE_SLOPE   else pd.Series(True, index=d.index)
    rsi_up     = (d["RSI_SLOPE"]   > 0) if USE_RSI_DIR else pd.Series(True, index=d.index)
    rsi_dn     = (d["RSI_SLOPE"]   < 0) if USE_RSI_DIR else pd.Series(True, index=d.index)

    long_sig  = (LONGS  & long_pb  & (d["Close"] > d["EMA_S"]) & (d["EMA_F"] > d["EMA_M"]) &
                 (d["RSI"] >= RSI_LO_L) & (d["RSI"] <= RSI_HI_L) &
                 (d["Volume"] >= d["VOL_MA"] * VOL_MULT) & is_trending & ~is_panic &
                 slope_ok_l & rsi_up)
    short_sig = (SHORTS & short_pb & (d["Close"] < d["EMA_S"]) & (d["EMA_F"] < d["EMA_M"]) &
                 (d["RSI"] >= RSI_LO_S) & (d["RSI"] <= RSI_HI_S) &
                 (d["Volume"] >= d["VOL_MA"] * VOL_MULT) & is_trending & ~is_panic &
                 slope_ok_s & rsi_dn)

    o = d["Open"].values;  h = d["High"].values
    l_= d["Low"].values;   c = d["Close"].values
    atr_v = d["ATR"].values; idx = d.index

    equity = INIT_CAP; in_trade = False; direction = None
    entry_px = sl_p = tp_p = best_p = entry_atr = qty = 0.0
    entry_time = None; trades = []
    l_sig_v = long_sig.values; s_sig_v = short_sig.values

    for i in range(len(d)):
        ca = atr_v[i]
        if np.isnan(ca) or ca == 0: continue
        eff = max(ca, c[i] * ATR_FLOOR)
        exited = False

        if in_trade:
            if direction == "long":
                if h[i] > best_p: best_p = h[i]
                if best_p >= entry_px + entry_atr * TRAIL_ACT:
                    t = best_p - entry_atr * TRAIL_DIST
                    if t > sl_p: sl_p = t
                if l_[i] <= sl_p:
                    ep = min(o[i], sl_p); pnl = (ep-entry_px)*qty
                    comm = (entry_px+ep)*qty*COMMISSION
                    equity += pnl-comm
                    trades.append({"dir":"long","entry":entry_px,"exit":ep,
                                   "pnl":pnl-comm,"eq":equity,"why":"SL/TR",
                                   "entry_t":entry_time,"exit_t":idx[i]})
                    in_trade=False; exited=True
                elif h[i] >= tp_p:
                    ep = max(o[i], tp_p); pnl = (ep-entry_px)*qty
                    comm = (entry_px+ep)*qty*COMMISSION
                    equity += pnl-comm
                    trades.append({"dir":"long","entry":entry_px,"exit":ep,
                                   "pnl":pnl-comm,"eq":equity,"why":"TP",
                                   "entry_t":entry_time,"exit_t":idx[i]})
                    in_trade=False; exited=True
            else:
                if l_[i] < best_p: best_p = l_[i]
                if best_p <= entry_px - entry_atr * TRAIL_ACT:
                    t = best_p + entry_atr * TRAIL_DIST
                    if t < sl_p: sl_p = t
                if h[i] >= sl_p:
                    ep = max(o[i], sl_p); pnl = (entry_px-ep)*qty
                    comm = (entry_px+ep)*qty*COMMISSION
                    equity += pnl-comm
                    trades.append({"dir":"short","entry":entry_px,"exit":ep,
                                   "pnl":pnl-comm,"eq":equity,"why":"SL/TR",
                                   "entry_t":entry_time,"exit_t":idx[i]})
                    in_trade=False; exited=True
                elif l_[i] <= tp_p:
                    ep = min(o[i], tp_p); pnl = (entry_px-ep)*qty
                    comm = (entry_px+ep)*qty*COMMISSION
                    equity += pnl-comm
                    trades.append({"dir":"short","entry":entry_px,"exit":ep,
                                   "pnl":pnl-comm,"eq":equity,"why":"TP",
                                   "entry_t":entry_time,"exit_t":idx[i]})
                    in_trade=False; exited=True

        if not in_trade:
            if l_sig_v[i]:
                sd = eff*SL_MULT; entry_px=c[i]; sl_p=entry_px-sd
                tp_p=entry_px+eff*TP_MULT; entry_atr=eff; best_p=entry_px
                qty=equity*RISK_PCT/sd; entry_time=idx[i]
                direction="long"; in_trade=True
            elif s_sig_v[i]:
                sd = eff*SL_MULT; entry_px=c[i]; sl_p=entry_px+sd
                tp_p=entry_px-eff*TP_MULT; entry_atr=eff; best_p=entry_px
                qty=equity*RISK_PCT/sd; entry_time=idx[i]
                direction="short"; in_trade=True

    if not trades:
        return {"pct": -999, "pf": 0, "wr": 0, "n": 0, "dd": -100,
                "nl": 0, "ns": 0, "wrl": 0, "wrs": 0}
    t = pd.DataFrame(trades)
    wins = t[t["pnl"] > 0]; losses = t[t["pnl"] <= 0]
    n  = len(t); wr = len(wins)/n*100
    gp = wins["pnl"].sum(); gl = abs(losses["pnl"].sum())
    pf = gp/gl if gl > 0 else 999
    pct = (equity-INIT_CAP)/INIT_CAP*100
    eq_a = t["eq"].values
    rm   = np.maximum.accumulate(np.concatenate([[INIT_CAP], eq_a]))
    dd   = ((np.concatenate([[INIT_CAP], eq_a]) - rm)/rm*100).min()
    nl = len(t[t["dir"]=="long"]); ns = len(t[t["dir"]=="short"])
    wrl = (t[t["dir"]=="long"]["pnl"]>0).mean()*100  if nl > 0 else 0
    wrs = (t[t["dir"]=="short"]["pnl"]>0).mean()*100 if ns > 0 else 0
    return {"pct": pct, "pf": pf, "wr": wr, "n": n, "dd": dd,
            "nl": nl, "ns": ns, "wrl": wrl, "wrs": wrs}

def hdr(title): print(f"\n{'─'*60}\n  {title}\n{'─'*60}")
def row(cfg, r, tag=""):
    print(f"  {tag:<32} n={r['n']:3d}  WR={r['wr']:5.1f}%  "
          f"PF={r['pf']:.3f}  {r['pct']:+.2f}%  DD={r['dd']:.1f}%")

# ── CLM v5 1h baseline ────────────────────────────────────────────────────────
BASE = {
    "adx": 20.0, "pb_pct": 0.20, "vol_mult": 0.70, "min_body": 0.20,
    "panic": 1.5, "sl": 1.5, "tp": 2.0, "trail_act": 2.5, "trail_dist": 0.5,
    "atr_floor": 0.0010, "ema_slope": True, "rsi_dir": False,
    "rsi_lo_l": 40.0, "rsi_hi_l": 70.0, "rsi_lo_s": 30.0, "rsi_hi_s": 60.0,
    "longs": True, "shorts": True,
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — ATR floor
# ─────────────────────────────────────────────────────────────────────────────
hdr("PHASE 1 — ATR floor")
ph1_best = None
for fl in [0.0, 0.0005, 0.0010, 0.0015, 0.0020]:
    cfg = {**BASE, "atr_floor": fl}
    r = backtest(cfg)
    row(cfg, r, f"ATR floor {fl*100:.2f}%")
    if ph1_best is None or r["pct"] > ph1_best[1]["pct"]: ph1_best = (cfg, r)
print(f"\n  ★ Best: ATR floor {ph1_best[0]['atr_floor']*100:.2f}%  → {ph1_best[1]['pct']:+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — EMA slope & RSI direction filters
# ─────────────────────────────────────────────────────────────────────────────
hdr("PHASE 2 — EMA slope & RSI direction filters")
p2_base = {**ph1_best[0]}
ph2_best = None
for slope, rdir in [(False,False),(True,False),(False,True),(True,True)]:
    cfg = {**p2_base, "ema_slope": slope, "rsi_dir": rdir}
    r = backtest(cfg)
    tag = ("slope+rsi_dir" if slope and rdir else
           "slope only"    if slope else
           "rsi_dir only"  if rdir else "neither (baseline)")
    row(cfg, r, tag)
    if ph2_best is None or r["pct"] > ph2_best[1]["pct"]: ph2_best = (cfg, r)
print(f"\n  ★ Best: ema_slope={ph2_best[0]['ema_slope']} "
      f"rsi_dir={ph2_best[0]['rsi_dir']}  → {ph2_best[1]['pct']:+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — TP × SL sweep
# ─────────────────────────────────────────────────────────────────────────────
hdr("PHASE 3 — TP × SL sweep")
p3_base = {**ph2_best[0]}
ph3_best = None
for sl in [1.0, 1.5, 2.0, 2.5]:
    for tp in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        cfg = {**p3_base, "sl": sl, "tp": tp}
        r = backtest(cfg)
        row(cfg, r, f"SL×{sl}  TP×{tp}")
        if ph3_best is None or r["pct"] > ph3_best[1]["pct"]: ph3_best = (cfg, r)
print(f"\n  ★ Best: SL×{ph3_best[0]['sl']} TP×{ph3_best[0]['tp']}  → {ph3_best[1]['pct']:+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 — ADX threshold
# ─────────────────────────────────────────────────────────────────────────────
hdr("PHASE 4 — ADX threshold")
p4_base = {**ph3_best[0]}
ph4_best = None
for adx in [12, 15, 18, 20, 23, 25, 28, 30]:
    cfg = {**p4_base, "adx": adx}
    r = backtest(cfg)
    row(cfg, r, f"ADX>{adx}")
    if ph4_best is None or r["pct"] > ph4_best[1]["pct"]: ph4_best = (cfg, r)
print(f"\n  ★ Best: ADX>{ph4_best[0]['adx']}  → {ph4_best[1]['pct']:+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5 — Trail activate × trail distance
# ─────────────────────────────────────────────────────────────────────────────
hdr("PHASE 5 — Trail activate × trail distance")
p5_base = {**ph4_best[0]}
ph5_best = None
for ta in [1.5, 2.0, 2.5, 3.0, 99.0]:
    for td in [0.3, 0.5, 0.8, 1.0, 1.5]:
        cfg = {**p5_base, "trail_act": ta, "trail_dist": td}
        r = backtest(cfg)
        ta_label = "off" if ta == 99.0 else f"act×{ta}"
        row(cfg, r, f"trail {ta_label}  dist×{td}")
        if ph5_best is None or r["pct"] > ph5_best[1]["pct"]: ph5_best = (cfg, r)
print(f"\n  ★ Best: trail_act×{ph5_best[0]['trail_act']} "
      f"trail_dist×{ph5_best[0]['trail_dist']}  → {ph5_best[1]['pct']:+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6 — Volume multiplier & min body
# ─────────────────────────────────────────────────────────────────────────────
hdr("PHASE 6 — Volume multiplier & min body")
p6_base = {**ph5_best[0]}
ph6_best = None
for vm in [0.5, 0.7, 0.9, 1.0, 1.2, 1.5]:
    for mb in [0.10, 0.15, 0.20, 0.25]:
        cfg = {**p6_base, "vol_mult": vm, "min_body": mb}
        r = backtest(cfg)
        row(cfg, r, f"vol×{vm}  body×{mb}")
        if ph6_best is None or r["pct"] > ph6_best[1]["pct"]: ph6_best = (cfg, r)
print(f"\n  ★ Best: vol×{ph6_best[0]['vol_mult']} "
      f"body×{ph6_best[0]['min_body']}  → {ph6_best[1]['pct']:+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 7 — RSI bands
# ─────────────────────────────────────────────────────────────────────────────
hdr("PHASE 7 — RSI bands (long & short)")
p7_base = {**ph6_best[0]}
ph7_best = None
for rlo_l, rhi_l, rlo_s, rhi_s in [
    (40, 70, 30, 60),
    (42, 72, 32, 62),
    (38, 68, 28, 58),
    (45, 72, 30, 60),
    (40, 65, 35, 65),
    (35, 70, 28, 65),
]:
    cfg = {**p7_base, "rsi_lo_l": rlo_l, "rsi_hi_l": rhi_l,
                      "rsi_lo_s": rlo_s, "rsi_hi_s": rhi_s}
    r = backtest(cfg)
    row(cfg, r, f"L:{rlo_l}-{rhi_l}  S:{rlo_s}-{rhi_s}")
    if ph7_best is None or r["pct"] > ph7_best[1]["pct"]: ph7_best = (cfg, r)
print(f"\n  ★ Best: L:{ph7_best[0]['rsi_lo_l']}-{ph7_best[0]['rsi_hi_l']}  "
      f"S:{ph7_best[0]['rsi_lo_s']}-{ph7_best[0]['rsi_hi_s']}  → {ph7_best[1]['pct']:+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 8 — Direction: longs / shorts / both
# ─────────────────────────────────────────────────────────────────────────────
hdr("PHASE 8 — Direction: longs / shorts / both")
p8_base = {**ph7_best[0]}
ph8_best = None
for lg, sh in [(True,True),(True,False),(False,True)]:
    cfg = {**p8_base, "longs": lg, "shorts": sh}
    r = backtest(cfg)
    tag = "both" if lg and sh else ("longs only" if lg else "shorts only")
    row(cfg, r, tag)
    if ph8_best is None or r["pct"] > ph8_best[1]["pct"]: ph8_best = (cfg, r)
print(f"\n  ★ Best: longs={ph8_best[0]['longs']} "
      f"shorts={ph8_best[0]['shorts']}  → {ph8_best[1]['pct']:+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
best_cfg, best_r = ph8_best
print(f"\n{'='*60}")
print(f"  OPTIMAL CONFIGURATION — CLM 1h  ({best_r['pct']:+.2f}% net)")
print(f"{'='*60}")
print(f"  ATR floor  : {best_cfg['atr_floor']*100:.2f}%")
print(f"  EMA slope  : {best_cfg['ema_slope']}")
print(f"  RSI dir    : {best_cfg['rsi_dir']}")
print(f"  ADX thresh : {best_cfg['adx']}")
print(f"  SL×        : {best_cfg['sl']}")
print(f"  TP×        : {best_cfg['tp']}")
print(f"  Trail act× : {best_cfg['trail_act']}")
print(f"  Trail dist×: {best_cfg['trail_dist']}")
print(f"  Vol mult   : {best_cfg['vol_mult']}")
print(f"  Min body   : {best_cfg['min_body']}")
print(f"  RSI L      : {best_cfg['rsi_lo_l']}-{best_cfg['rsi_hi_l']}")
print(f"  RSI S      : {best_cfg['rsi_lo_s']}-{best_cfg['rsi_hi_s']}")
print(f"  Longs      : {best_cfg['longs']}")
print(f"  Shorts     : {best_cfg['shorts']}")
print(f"  ─────────────────────────────────────────────────────")
print(f"  Trades     : {best_r['n']}  (L={best_r['nl']}, S={best_r['ns']})")
print(f"  Win rate   : {best_r['wr']:.1f}%  (L WR={best_r['wrl']:.1f}%, S WR={best_r['wrs']:.1f}%)")
print(f"  Profit fac : {best_r['pf']:.3f}")
print(f"  Net return : {best_r['pct']:+.2f}%")
print(f"  Max DD     : {best_r['dd']:.2f}%")
print(f"{'='*60}")
