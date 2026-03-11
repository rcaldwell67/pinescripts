"""
Deep sweep — APM v3 @ 1h CLM
Continuation from extended sweep optimal:
  ADX=33, SL×2.0, TP×2.0, Panic×1.4, Vol×1.2, Body×0.10
  Trail OFF, EMA slope OFF, ATR floor 0%, RSI L:40-70 / S:30-60

Explores dimensions not yet varied:
  H. EMA fast / mid period lengths
  I. ADX period length
  J. RSI period length
  K. Volume MA period length
  L. Time-of-day filter (US session: 9-16 ET = 14-21 UTC, crude oil peak liquidity)
  M. ATR period length
  N. Joint panic × ADX fine grid (best so far has few trades — validate stability)
  O. ATR baseline length (affects panic detection)

Min-trade guard: n >= 10 to report, n >= 12 for final winner.
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

# ── Cached indicator sets per (ema_f, ema_m, ema_s, adx_len, rsi_len, vol_len, atr_len, atr_bl_len)
_ind_cache = {}

def get_indicators(ema_f=21, ema_m=50, ema_s=200, adx_len=14,
                   rsi_len=14, vol_len=20, atr_len=14, atr_bl_len=50):
    key = (ema_f, ema_m, ema_s, adx_len, rsi_len, vol_len, atr_len, atr_bl_len)
    if key in _ind_cache:
        return _ind_cache[key]

    d = df_raw.copy()
    def ema(s, n):  return s.ewm(span=n, adjust=False).mean()
    def rsi_fn(s, n):
        δ = s.diff()
        u = δ.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        v = (-δ).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        return 100 - 100/(1 + u/v.replace(0, np.nan))
    def atr_fn(h, l, c, n):
        tr = pd.concat([h-l,(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)
        return tr.ewm(alpha=1/n, adjust=False).mean()
    def adx_fn(h, l, c, n):
        up = h.diff(); dn = -l.diff()
        pdm = up.where((up > dn) & (up > 0), 0.0)
        ndm = dn.where((dn > up) & (dn > 0), 0.0)
        tr14 = atr_fn(h, l, c, n)
        pdi = 100*pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
        ndi = 100*ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
        dx  = 100*(pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan)
        return dx.ewm(alpha=1/n, adjust=False).mean()

    d["EMA_F"]  = ema(d["Close"], ema_f)
    d["EMA_M"]  = ema(d["Close"], ema_m)
    d["EMA_S"]  = ema(d["Close"], ema_s)
    d["ATR"]    = atr_fn(d["High"], d["Low"], d["Close"], atr_len)
    d["ATR_BL"] = d["ATR"].rolling(atr_bl_len).mean()
    d["ADX"]    = adx_fn(d["High"], d["Low"], d["Close"], adx_len)
    d["RSI"]    = rsi_fn(d["Close"], rsi_len)
    d["VOL_MA"] = d["Volume"].rolling(vol_len).mean()
    d["BODY"]   = (d["Close"]-d["Open"]).abs() / d["ATR"].replace(0, np.nan)
    d["EMA_F_SLOPE"] = d["EMA_F"] - d["EMA_F"].shift(3)
    d = d.dropna()
    _ind_cache[key] = d
    return d

# ── Core backtest engine ───────────────────────────────────────────────────────
def backtest(cfg):
    ADX_THRESH  = cfg.get("adx",        33.0)
    PB_PCT      = cfg.get("pb_pct",     0.20)
    VOL_MULT    = cfg.get("vol_mult",   1.20)
    MIN_BODY    = cfg.get("min_body",   0.10)
    PANIC_MULT  = cfg.get("panic",      1.4)
    SL_MULT     = cfg.get("sl",         2.0)
    TP_MULT     = cfg.get("tp",         2.0)
    TRAIL_ACT   = cfg.get("trail_act",  99.0)
    TRAIL_DIST  = cfg.get("trail_dist", 0.3)
    ATR_FLOOR   = cfg.get("atr_floor",  0.0)
    RSI_LO_L    = cfg.get("rsi_lo_l",  40.0); RSI_HI_L = cfg.get("rsi_hi_l", 70.0)
    RSI_LO_S    = cfg.get("rsi_lo_s",  30.0); RSI_HI_S = cfg.get("rsi_hi_s", 60.0)
    USE_SLOPE   = cfg.get("ema_slope",  False)
    LONGS       = cfg.get("longs",      True)
    SHORTS      = cfg.get("shorts",     True)
    TOD_FILTER  = cfg.get("tod_filter", False)  # time-of-day filter
    TOD_START   = cfg.get("tod_start",  14)      # UTC hour start (inclusive)
    TOD_END     = cfg.get("tod_end",    21)      # UTC hour end (exclusive)

    EMA_F_LEN   = cfg.get("ema_f",      21)
    EMA_M_LEN   = cfg.get("ema_m",      50)
    EMA_S_LEN   = cfg.get("ema_s",      200)
    ADX_LEN     = cfg.get("adx_len",    14)
    RSI_LEN     = cfg.get("rsi_len",    14)
    VOL_LEN     = cfg.get("vol_len",    20)
    ATR_LEN     = cfg.get("atr_len",    14)
    ATR_BL_LEN  = cfg.get("atr_bl_len", 50)

    d = get_indicators(EMA_F_LEN, EMA_M_LEN, EMA_S_LEN, ADX_LEN,
                       RSI_LEN, VOL_LEN, ATR_LEN, ATR_BL_LEN)

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

    if TOD_FILTER:
        hour = d.index.hour
        in_session = pd.Series((hour >= TOD_START) & (hour < TOD_END), index=d.index)
    else:
        in_session = pd.Series(True, index=d.index)

    long_sig  = (LONGS  & long_pb  & (d["Close"] > d["EMA_S"]) & (d["EMA_F"] > d["EMA_M"]) &
                 (d["RSI"] >= RSI_LO_L) & (d["RSI"] <= RSI_HI_L) &
                 (d["Volume"] >= d["VOL_MA"] * VOL_MULT) & is_trending & ~is_panic &
                 slope_ok_l & in_session)
    short_sig = (SHORTS & short_pb & (d["Close"] < d["EMA_S"]) & (d["EMA_F"] < d["EMA_M"]) &
                 (d["RSI"] >= RSI_LO_S) & (d["RSI"] <= RSI_HI_S) &
                 (d["Volume"] >= d["VOL_MA"] * VOL_MULT) & is_trending & ~is_panic &
                 slope_ok_s & in_session)

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
                    ep = min(o[i], sl_p); net = (ep-entry_px)*qty - (entry_px+ep)*qty*COMMISSION
                    equity += net
                    trades.append({"dir":"long","pnl":net,"eq":equity,"why":"SL/TR"})
                    in_trade=False; exited=True
                elif h[i] >= tp_p:
                    ep = max(o[i], tp_p); net = (ep-entry_px)*qty - (entry_px+ep)*qty*COMMISSION
                    equity += net
                    trades.append({"dir":"long","pnl":net,"eq":equity,"why":"TP"})
                    in_trade=False; exited=True
            else:
                if l_[i] < best_p: best_p = l_[i]
                if best_p <= entry_px - entry_atr * TRAIL_ACT:
                    t = best_p + entry_atr * TRAIL_DIST
                    if t < sl_p: sl_p = t
                if h[i] >= sl_p:
                    ep = max(o[i], sl_p); net = (entry_px-ep)*qty - (entry_px+ep)*qty*COMMISSION
                    equity += net
                    trades.append({"dir":"short","pnl":net,"eq":equity,"why":"SL/TR"})
                    in_trade=False; exited=True
                elif l_[i] <= tp_p:
                    ep = min(o[i], tp_p); net = (entry_px-ep)*qty - (entry_px+ep)*qty*COMMISSION
                    equity += net
                    trades.append({"dir":"short","pnl":net,"eq":equity,"why":"TP"})
                    in_trade=False; exited=True

        if not in_trade:
            if l_sig_v[i]:
                sd = eff*SL_MULT; entry_px=c[i]; sl_p=entry_px-sd
                tp_p=entry_px+eff*TP_MULT; entry_atr=eff; best_p=entry_px
                qty=equity*RISK_PCT/sd; entry_time=idx[i]; direction="long"; in_trade=True
            elif s_sig_v[i]:
                sd = eff*SL_MULT; entry_px=c[i]; sl_p=entry_px+sd
                tp_p=entry_px-eff*TP_MULT; entry_atr=eff; best_p=entry_px
                qty=equity*RISK_PCT/sd; entry_time=idx[i]; direction="short"; in_trade=True

    if not trades:
        return {"pct": -999, "pf": 0, "wr": 0, "n": 0, "dd": -100, "nl": 0, "ns": 0}
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

# Extended sweep optimal (starting point)
OPT = {
    "adx": 33.0, "pb_pct": 0.20, "vol_mult": 1.20, "min_body": 0.10,
    "panic": 1.4, "sl": 2.0, "tp": 2.0, "trail_act": 99.0, "trail_dist": 0.3,
    "atr_floor": 0.0, "ema_slope": False, "longs": True, "shorts": True,
    "rsi_lo_l": 40.0, "rsi_hi_l": 70.0, "rsi_lo_s": 30.0, "rsi_hi_s": 60.0,
    "ema_f": 21, "ema_m": 50, "ema_s": 200,
    "adx_len": 14, "rsi_len": 14, "vol_len": 20, "atr_len": 14, "atr_bl_len": 50,
    "tod_filter": False, "tod_start": 14, "tod_end": 21,
}

def hdr(t): print(f"\n{'─'*64}\n  {t}\n{'─'*64}")
def row(r, tag=""):
    if r["n"] < 10: return   # skip thin configs
    print(f"  {tag:<40} n={r['n']:3d}  WR={r['wr']:5.1f}%  "
          f"PF={r['pf']:.3f}  {r['pct']:+.2f}%  DD={r['dd']:.1f}%")

overall_best = (OPT, backtest(OPT))
def maybe_best(cfg, r):
    global overall_best
    if r["pct"] > overall_best[1]["pct"] and r["n"] >= 12:
        overall_best = (cfg, r)

# ── H. EMA fast / mid period lengths ─────────────────────────────────────────
hdr("H — EMA fast/mid period lengths (slow fixed at 200)")
phH_best = None
for ef, em in itertools.product([9, 13, 21, 34], [34, 50, 89]):
    if em <= ef: continue
    cfg = {**OPT, "ema_f": ef, "ema_m": em}
    r = backtest(cfg)
    row(r, f"EMA {ef}/{em}/200")
    maybe_best(cfg, r)
    if phH_best is None or r["pct"] > phH_best[1]["pct"]: phH_best = (cfg, r)
print(f"\n  ★ Best: EMA {phH_best[0]['ema_f']}/{phH_best[0]['ema_m']}/200  "
      f"→ {phH_best[1]['pct']:+.2f}%  PF={phH_best[1]['pf']:.3f}  n={phH_best[1]['n']}")

# ── I. ADX period length ──────────────────────────────────────────────────────
hdr("I — ADX period length")
phI_best = None
for al in [7, 10, 12, 14, 18, 21]:
    cfg = {**phH_best[0], "adx_len": al}
    r = backtest(cfg)
    row(r, f"ADX period {al}")
    maybe_best(cfg, r)
    if phI_best is None or r["pct"] > phI_best[1]["pct"]: phI_best = (cfg, r)
print(f"\n  ★ Best: ADX period {phI_best[0]['adx_len']}  "
      f"→ {phI_best[1]['pct']:+.2f}%  PF={phI_best[1]['pf']:.3f}  n={phI_best[1]['n']}")

# ── J. RSI period length ──────────────────────────────────────────────────────
hdr("J — RSI period length")
phJ_best = None
for rl in [7, 9, 10, 12, 14, 20]:
    cfg = {**phI_best[0], "rsi_len": rl}
    r = backtest(cfg)
    row(r, f"RSI period {rl}")
    maybe_best(cfg, r)
    if phJ_best is None or r["pct"] > phJ_best[1]["pct"]: phJ_best = (cfg, r)
print(f"\n  ★ Best: RSI period {phJ_best[0]['rsi_len']}  "
      f"→ {phJ_best[1]['pct']:+.2f}%  PF={phJ_best[1]['pf']:.3f}  n={phJ_best[1]['n']}")

# ── K. Volume MA period length ────────────────────────────────────────────────
hdr("K — Volume MA period length")
phK_best = None
for vl in [10, 15, 20, 30, 40]:
    cfg = {**phJ_best[0], "vol_len": vl}
    r = backtest(cfg)
    row(r, f"Vol MA period {vl}")
    maybe_best(cfg, r)
    if phK_best is None or r["pct"] > phK_best[1]["pct"]: phK_best = (cfg, r)
print(f"\n  ★ Best: Vol MA period {phK_best[0]['vol_len']}  "
      f"→ {phK_best[1]['pct']:+.2f}%  PF={phK_best[1]['pf']:.3f}  n={phK_best[1]['n']}")

# ── L. Time-of-day filter (UTC hours, crude oil US session) ──────────────────
hdr("L — Time-of-day filter (UTC hours, crude oil liquidity windows)")
# CLM trades on CME. US session: ~13:00-20:00 UTC (9am-4pm ET)
# Asian/London overlap: 07:00-13:00 UTC
# Full session off = no filter
phL_best = None
windows = [
    (False, 0,  24, "no filter"),
    (True,  13, 20, "US session 13-20 UTC"),
    (True,  12, 21, "US session 12-21 UTC"),
    (True,  13, 21, "US session 13-21 UTC"),
    (True,  14, 20, "US session 14-20 UTC"),
    (True,   8, 20, "London+US 8-20 UTC"),
    (True,   7, 13, "London session 7-13 UTC"),
    (True,  13, 16, "US morning 13-16 UTC"),
]
for tod, ts, te, label in windows:
    cfg = {**phK_best[0], "tod_filter": tod, "tod_start": ts, "tod_end": te}
    r = backtest(cfg)
    row(r, label)
    maybe_best(cfg, r)
    if phL_best is None or r["pct"] > phL_best[1]["pct"]: phL_best = (cfg, r)
print(f"\n  ★ Best: tod={phL_best[0]['tod_filter']} "
      f"{phL_best[0]['tod_start']}-{phL_best[0]['tod_end']} UTC  "
      f"→ {phL_best[1]['pct']:+.2f}%  PF={phL_best[1]['pf']:.3f}  n={phL_best[1]['n']}")

# ── M. ATR period & ATR baseline length ──────────────────────────────────────
hdr("M — ATR period & ATR baseline length")
phM_best = None
for al, bl in itertools.product([10, 12, 14, 18], [30, 50, 75, 100]):
    cfg = {**phL_best[0], "atr_len": al, "atr_bl_len": bl}
    r = backtest(cfg)
    row(r, f"ATR period {al}  baseline {bl}")
    maybe_best(cfg, r)
    if phM_best is None or r["pct"] > phM_best[1]["pct"]: phM_best = (cfg, r)
print(f"\n  ★ Best: ATR period {phM_best[0]['atr_len']}  "
      f"baseline {phM_best[0]['atr_bl_len']}  "
      f"→ {phM_best[1]['pct']:+.2f}%  PF={phM_best[1]['pf']:.3f}  n={phM_best[1]['n']}")

# ── N. Joint panic × ADX fine grid ───────────────────────────────────────────
hdr("N — Joint panic × ADX fine grid (stability check)")
phN_best = None
for pm, adx in itertools.product([1.3, 1.35, 1.4, 1.45, 1.5, 1.6],
                                  [31, 32, 33, 34, 35]):
    cfg = {**phM_best[0], "panic": pm, "adx": adx}
    r = backtest(cfg)
    row(r, f"panic×{pm}  ADX>{adx}")
    maybe_best(cfg, r)
    if phN_best is None or r["pct"] > phN_best[1]["pct"]: phN_best = (cfg, r)
print(f"\n  ★ Best: panic×{phN_best[0]['panic']}  ADX>{phN_best[0]['adx']}  "
      f"→ {phN_best[1]['pct']:+.2f}%  PF={phN_best[1]['pf']:.3f}  n={phN_best[1]['n']}")

# ── O. Joint VOL_MULT × MIN_BODY fine grid ────────────────────────────────────
hdr("O — Joint VOL_MULT × MIN_BODY fine grid")
phO_best = None
for vm, mb in itertools.product([0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
                                 [0.05, 0.10, 0.15, 0.20]):
    cfg = {**phN_best[0], "vol_mult": vm, "min_body": mb}
    r = backtest(cfg)
    row(r, f"Vol×{vm}  Body×{mb}")
    maybe_best(cfg, r)
    if phO_best is None or r["pct"] > phO_best[1]["pct"]: phO_best = (cfg, r)
print(f"\n  ★ Best: Vol×{phO_best[0]['vol_mult']}  Body×{phO_best[0]['min_body']}  "
      f"→ {phO_best[1]['pct']:+.2f}%  PF={phO_best[1]['pf']:.3f}  n={phO_best[1]['n']}")

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
final_cfg, final_r = phO_best

print(f"\n{'='*64}")
print(f"  DEEP SWEEP — BEST CONFIG — CLM 1h  ({final_r['pct']:+.2f}% net)")
print(f"{'='*64}")
print(f"  EMA fast/mid/slow : {final_cfg['ema_f']}/{final_cfg['ema_m']}/{final_cfg['ema_s']}")
print(f"  ADX thresh / len  : {final_cfg['adx']} / period {final_cfg['adx_len']}")
print(f"  RSI len           : {final_cfg['rsi_len']}")
print(f"  ATR len / BL len  : {final_cfg['atr_len']} / {final_cfg['atr_bl_len']}")
print(f"  Vol MA len        : {final_cfg['vol_len']}")
print(f"  PB_PCT            : {final_cfg['pb_pct']:.2f}%")
print(f"  SL×               : {final_cfg['sl']}")
print(f"  TP×               : {final_cfg['tp']}")
print(f"  Vol mult          : {final_cfg['vol_mult']}")
print(f"  Min body          : {final_cfg['min_body']}")
print(f"  Panic×            : {final_cfg['panic']}")
print(f"  Trail act×        : {final_cfg['trail_act']}")
print(f"  EMA slope         : {final_cfg['ema_slope']}")
print(f"  ATR floor         : {final_cfg['atr_floor']*100:.2f}%")
print(f"  ToD filter        : {final_cfg['tod_filter']}  "
      f"{final_cfg['tod_start']}-{final_cfg['tod_end']} UTC")
print(f"  RSI L / S         : {final_cfg['rsi_lo_l']}-{final_cfg['rsi_hi_l']} / "
      f"{final_cfg['rsi_lo_s']}-{final_cfg['rsi_hi_s']}")
print(f"  Longs / Shorts    : {final_cfg['longs']} / {final_cfg['shorts']}")
print(f"  ────────────────────────────────────────────────────────────")
print(f"  Trades     : {final_r['n']}  (L={final_r['nl']}, S={final_r['ns']})")
print(f"  Win rate   : {final_r['wr']:.1f}%")
print(f"  Profit fac : {final_r['pf']:.3f}")
print(f"  Net return : {final_r['pct']:+.2f}%")
print(f"  Max DD     : {final_r['dd']:.2f}%")
print(f"{'='*64}")
