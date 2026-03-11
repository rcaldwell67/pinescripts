"""
Extended sweep — APM v3 @ 1h CLM
Continuation from Phase 1-8 sweep optimal:
  ADX=30, SL×2.5, TP×2.0, Trail OFF, Vol×1.2, Body×0.10
  EMA slope OFF, ATR floor 0%, RSI L:40-70 / S:30-60, Longs+Shorts

Explores dimensions not covered in Phase 1-8:
  A. Fine-grained ADX (28..42 step 1)
  B. PB_PCT (never varied in prior sweep)
  C. PANIC_MULT (never varied in prior sweep)
  D. TP fine-grained around optimum
  E. Joint ADX × SL × TP grid
  F. Joint VOL × ADX grid
  G. Full joint grid search on top-3 params from best cfg so far
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings, itertools
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

# ── Indicators ─────────────────────────────────────────────────────────────────
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
    ADX_THRESH = cfg.get("adx",        30.0)
    PB_PCT     = cfg.get("pb_pct",     0.20)
    VOL_MULT   = cfg.get("vol_mult",   1.20)
    MIN_BODY   = cfg.get("min_body",   0.10)
    PANIC_MULT = cfg.get("panic",      1.5)
    SL_MULT    = cfg.get("sl",         2.5)
    TP_MULT    = cfg.get("tp",         2.0)
    TRAIL_ACT  = cfg.get("trail_act",  99.0)
    TRAIL_DIST = cfg.get("trail_dist", 0.3)
    ATR_FLOOR  = cfg.get("atr_floor",  0.0)
    RSI_LO_L   = cfg.get("rsi_lo_l",  40.0); RSI_HI_L = cfg.get("rsi_hi_l", 70.0)
    RSI_LO_S   = cfg.get("rsi_lo_s",  30.0); RSI_HI_S = cfg.get("rsi_hi_s", 60.0)
    USE_SLOPE  = cfg.get("ema_slope",  False)
    LONGS      = cfg.get("longs",      True)
    SHORTS     = cfg.get("shorts",     True)

    d = df.copy()
    pb_up = d["EMA_F"].shift(1) * (1 + PB_PCT/100)
    pb_dn = d["EMA_F"].shift(1) * (1 - PB_PCT/100)
    long_pb  = (d["Low"].shift(1)  <= pb_up) & (d["Close"] > d["EMA_F"]) & \
               (d["Close"] > d["Open"]) & (d["BODY"] >= MIN_BODY)
    short_pb = (d["High"].shift(1) >= pb_dn) & (d["Close"] < d["EMA_F"]) & \
               (d["Close"] < d["Open"]) & (d["BODY"] >= MIN_BODY)

    is_trending = d["ADX"] > ADX_THRESH
    is_panic    = d["ATR"] > d["ATR_BL"] * PANIC_MULT

    slope_ok_l = (d["EMA_F_SLOPE"] > 0) if USE_SLOPE else pd.Series(True, index=d.index)
    slope_ok_s = (d["EMA_F_SLOPE"] < 0) if USE_SLOPE else pd.Series(True, index=d.index)

    long_sig  = (LONGS  & long_pb  & (d["Close"] > d["EMA_S"]) & (d["EMA_F"] > d["EMA_M"]) &
                 (d["RSI"] >= RSI_LO_L) & (d["RSI"] <= RSI_HI_L) &
                 (d["Volume"] >= d["VOL_MA"] * VOL_MULT) & is_trending & ~is_panic & slope_ok_l)
    short_sig = (SHORTS & short_pb & (d["Close"] < d["EMA_S"]) & (d["EMA_F"] < d["EMA_M"]) &
                 (d["RSI"] >= RSI_LO_S) & (d["RSI"] <= RSI_HI_S) &
                 (d["Volume"] >= d["VOL_MA"] * VOL_MULT) & is_trending & ~is_panic & slope_ok_s)

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
                    equity += pnl - (entry_px+ep)*qty*COMMISSION
                    trades.append({"dir":"long","pnl":pnl-(entry_px+ep)*qty*COMMISSION,
                                   "eq":equity,"why":"SL/TR"})
                    in_trade=False; exited=True
                elif h[i] >= tp_p:
                    ep = max(o[i], tp_p); pnl = (ep-entry_px)*qty
                    equity += pnl - (entry_px+ep)*qty*COMMISSION
                    trades.append({"dir":"long","pnl":pnl-(entry_px+ep)*qty*COMMISSION,
                                   "eq":equity,"why":"TP"})
                    in_trade=False; exited=True
            else:
                if l_[i] < best_p: best_p = l_[i]
                if best_p <= entry_px - entry_atr * TRAIL_ACT:
                    t = best_p + entry_atr * TRAIL_DIST
                    if t < sl_p: sl_p = t
                if h[i] >= sl_p:
                    ep = max(o[i], sl_p); pnl = (entry_px-ep)*qty
                    equity += pnl - (entry_px+ep)*qty*COMMISSION
                    trades.append({"dir":"short","pnl":pnl-(entry_px+ep)*qty*COMMISSION,
                                   "eq":equity,"why":"SL/TR"})
                    in_trade=False; exited=True
                elif l_[i] <= tp_p:
                    ep = min(o[i], tp_p); pnl = (entry_px-ep)*qty
                    equity += pnl - (entry_px+ep)*qty*COMMISSION
                    trades.append({"dir":"short","pnl":pnl-(entry_px+ep)*qty*COMMISSION,
                                   "eq":equity,"why":"TP"})
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
                "nl": 0, "ns": 0}
    t = pd.DataFrame(trades)
    wins = t[t["pnl"] > 0]; losses = t[t["pnl"] <= 0]
    n = len(t); wr = len(wins)/n*100
    gp = wins["pnl"].sum(); gl = abs(losses["pnl"].sum())
    pf = gp/gl if gl > 0 else 999
    pct = (equity-INIT_CAP)/INIT_CAP*100
    eq_a = t["eq"].values
    rm   = np.maximum.accumulate(np.concatenate([[INIT_CAP], eq_a]))
    dd   = ((np.concatenate([[INIT_CAP], eq_a]) - rm)/rm*100).min()
    nl = len(t[t["dir"]=="long"]); ns = len(t[t["dir"]=="short"])
    return {"pct": pct, "pf": pf, "wr": wr, "n": n, "dd": dd, "nl": nl, "ns": ns}

# Phase 1-8 optimal baseline
OPT = {
    "adx": 30.0, "pb_pct": 0.20, "vol_mult": 1.20, "min_body": 0.10,
    "panic": 1.5, "sl": 2.5, "tp": 2.0, "trail_act": 99.0, "trail_dist": 0.3,
    "atr_floor": 0.0, "ema_slope": False, "longs": True, "shorts": True,
    "rsi_lo_l": 40.0, "rsi_hi_l": 70.0, "rsi_lo_s": 30.0, "rsi_hi_s": 60.0,
}

def hdr(t): print(f"\n{'─'*62}\n  {t}\n{'─'*62}")
def row(r, tag=""):
    print(f"  {tag:<36} n={r['n']:3d}  WR={r['wr']:5.1f}%  "
          f"PF={r['pf']:.3f}  {r['pct']:+.2f}%  DD={r['dd']:.1f}%")

overall_best = (OPT, backtest(OPT))

def maybe_best(cfg, r):
    global overall_best
    if r["pct"] > overall_best[1]["pct"] and r["n"] >= 10:
        overall_best = (cfg, r)

# ── A. Fine-grained ADX ───────────────────────────────────────────────────────
hdr("A — Fine-grained ADX (28..42)")
phA_best = None
for adx in range(28, 43):
    cfg = {**OPT, "adx": adx}
    r = backtest(cfg)
    row(r, f"ADX>{adx}")
    maybe_best(cfg, r)
    if phA_best is None or r["pct"] > phA_best[1]["pct"]: phA_best = (cfg, r)
print(f"\n  ★ Best: ADX>{phA_best[0]['adx']}  → {phA_best[1]['pct']:+.2f}%  "
      f"PF={phA_best[1]['pf']:.3f}  n={phA_best[1]['n']}")

# ── B. PB_PCT sweep ───────────────────────────────────────────────────────────
hdr("B — Pullback tolerance PB_PCT (0.05 .. 0.40)")
phB_best = None
for pb in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]:
    cfg = {**phA_best[0], "pb_pct": pb}
    r = backtest(cfg)
    row(r, f"PB_PCT {pb:.2f}%")
    maybe_best(cfg, r)
    if phB_best is None or r["pct"] > phB_best[1]["pct"]: phB_best = (cfg, r)
print(f"\n  ★ Best: PB_PCT={phB_best[0]['pb_pct']:.2f}%  → {phB_best[1]['pct']:+.2f}%  "
      f"PF={phB_best[1]['pf']:.3f}  n={phB_best[1]['n']}")

# ── C. PANIC_MULT sweep ───────────────────────────────────────────────────────
hdr("C — Panic multiplier (1.0 .. 3.0, OFF)")
phC_best = None
for pm in [1.0, 1.2, 1.4, 1.5, 1.6, 1.8, 2.0, 2.5, 3.0, 999.0]:
    cfg = {**phB_best[0], "panic": pm}
    r = backtest(cfg)
    label = "OFF" if pm == 999.0 else f"panic×{pm}"
    row(r, label)
    maybe_best(cfg, r)
    if phC_best is None or r["pct"] > phC_best[1]["pct"]: phC_best = (cfg, r)
print(f"\n  ★ Best: panic×{phC_best[0]['panic']}  → {phC_best[1]['pct']:+.2f}%  "
      f"PF={phC_best[1]['pf']:.3f}  n={phC_best[1]['n']}")

# ── D. TP fine-grained around optimum ─────────────────────────────────────────
hdr("D — TP fine-grained (1.5 .. 3.5 step 0.25)")
phD_best = None
for tp in [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5]:
    cfg = {**phC_best[0], "tp": tp}
    r = backtest(cfg)
    row(r, f"TP×{tp}")
    maybe_best(cfg, r)
    if phD_best is None or r["pct"] > phD_best[1]["pct"]: phD_best = (cfg, r)
print(f"\n  ★ Best: TP×{phD_best[0]['tp']}  → {phD_best[1]['pct']:+.2f}%  "
      f"PF={phD_best[1]['pf']:.3f}  n={phD_best[1]['n']}")

# ── E. Joint ADX × SL × TP grid ──────────────────────────────────────────────
hdr("E — Joint ADX × SL × TP grid")
adx_vals = [phD_best[0]["adx"] - 2, phD_best[0]["adx"], phD_best[0]["adx"] + 2]
sl_vals  = [2.0, 2.5, 3.0]
tp_vals  = [1.75, 2.0, 2.25, 2.5, 3.0]
phE_best = None
for adx, sl, tp in itertools.product(adx_vals, sl_vals, tp_vals):
    cfg = {**phD_best[0], "adx": adx, "sl": sl, "tp": tp}
    r = backtest(cfg)
    row(r, f"ADX>{adx}  SL×{sl}  TP×{tp}")
    maybe_best(cfg, r)
    if phE_best is None or r["pct"] > phE_best[1]["pct"]: phE_best = (cfg, r)
print(f"\n  ★ Best: ADX>{phE_best[0]['adx']}  SL×{phE_best[0]['sl']}  TP×{phE_best[0]['tp']}  "
      f"→ {phE_best[1]['pct']:+.2f}%  PF={phE_best[1]['pf']:.3f}  n={phE_best[1]['n']}")

# ── F. Joint VOL × ADX grid ───────────────────────────────────────────────────
hdr("F — Joint VOL × ADX grid")
vol_vals = [0.9, 1.0, 1.2, 1.4, 1.5, 1.8]
adx_f   = [phE_best[0]["adx"] - 2, phE_best[0]["adx"], phE_best[0]["adx"] + 2]
phF_best = None
for adx, vm in itertools.product(adx_f, vol_vals):
    cfg = {**phE_best[0], "adx": adx, "vol_mult": vm}
    r = backtest(cfg)
    row(r, f"ADX>{adx}  Vol×{vm}")
    maybe_best(cfg, r)
    if phF_best is None or r["pct"] > phF_best[1]["pct"]: phF_best = (cfg, r)
print(f"\n  ★ Best: ADX>{phF_best[0]['adx']}  Vol×{phF_best[0]['vol_mult']}  "
      f"→ {phF_best[1]['pct']:+.2f}%  PF={phF_best[1]['pf']:.3f}  n={phF_best[1]['n']}")

# ── G. Min trade count filter — recheck best at ≥15 trades ───────────────────
hdr("G — Top candidates (n≥15) from entire sweep")
# Re-scan a targeted grid around the overall best
best_adx  = overall_best[0]["adx"]
best_sl   = overall_best[0]["sl"]
best_tp   = overall_best[0]["tp"]
best_vm   = overall_best[0]["vol_mult"]
best_pb   = overall_best[0]["pb_pct"]
best_panic= overall_best[0]["panic"]

candidates = []
for adx in [best_adx-2, best_adx-1, best_adx, best_adx+1, best_adx+2]:
    for sl in [best_sl-0.5, best_sl, best_sl+0.5]:
        for tp in [best_tp-0.25, best_tp, best_tp+0.25]:
            for vm in [best_vm-0.2, best_vm, best_vm+0.2]:
                cfg = {**overall_best[0], "adx": adx, "sl": sl, "tp": tp, "vol_mult": vm}
                r = backtest(cfg)
                if r["n"] >= 15:
                    candidates.append((cfg, r))

candidates.sort(key=lambda x: x[1]["pct"], reverse=True)
for cfg, r in candidates[:15]:
    row(r, f"ADX>{cfg['adx']}  SL×{cfg['sl']}  TP×{cfg['tp']}  Vol×{cfg['vol_mult']}")

if candidates:
    phG_best = candidates[0]
else:
    phG_best = overall_best

print(f"\n  ★ Best (n≥15): → {phG_best[1]['pct']:+.2f}%  "
      f"PF={phG_best[1]['pf']:.3f}  n={phG_best[1]['n']}")

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
# Pick best from G if it beats overall_best by return, else keep overall_best
final_cfg, final_r = (phG_best if phG_best[1]["pct"] > overall_best[1]["pct"]
                      else overall_best)

print(f"\n{'='*62}")
print(f"  EXTENDED SWEEP — BEST CONFIG — CLM 1h  ({final_r['pct']:+.2f}% net)")
print(f"{'='*62}")
print(f"  ADX thresh : {final_cfg['adx']}")
print(f"  PB_PCT     : {final_cfg['pb_pct']:.2f}%")
print(f"  SL×        : {final_cfg['sl']}")
print(f"  TP×        : {final_cfg['tp']}")
print(f"  Vol mult   : {final_cfg['vol_mult']}")
print(f"  Min body   : {final_cfg['min_body']}")
print(f"  Panic×     : {final_cfg['panic']}")
print(f"  Trail act× : {final_cfg['trail_act']}")
print(f"  EMA slope  : {final_cfg['ema_slope']}")
print(f"  ATR floor  : {final_cfg['atr_floor']*100:.2f}%")
print(f"  RSI L      : {final_cfg['rsi_lo_l']}-{final_cfg['rsi_hi_l']}")
print(f"  RSI S      : {final_cfg['rsi_lo_s']}-{final_cfg['rsi_hi_s']}")
print(f"  Longs      : {final_cfg['longs']}")
print(f"  Shorts     : {final_cfg['shorts']}")
print(f"  ──────────────────────────────────────────────────────")
print(f"  Trades     : {final_r['n']}  (L={final_r['nl']}, S={final_r['ns']})")
print(f"  Win rate   : {final_r['wr']:.1f}%")
print(f"  Profit fac : {final_r['pf']:.3f}")
print(f"  Net return : {final_r['pct']:+.2f}%")
print(f"  Max DD     : {final_r['dd']:.2f}%")
print(f"{'='*62}")
