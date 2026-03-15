"""
sweep_apm_v5_1h_s1.py — APM v5 CLM 1h   Stage-1 max-return sweep
=================================================================
Axes:
  TP_MULT   : 2.0, 3.0, 5.0, 8.0, 12.0
  TRAIL_ACT : 2.0, 3.0, 99.0 (99=off)
  ADX       : 15, 20, 25, 30
  PB_PCT    : 0.10, 0.20, 0.40
  SL_MULT   : 1.0, 1.5, 2.0
  DIRS      : longs_only, both

Total combos : 5×3×4×3×3×2 = 1080  — fast (vectorised signal gen)

Filter  : n >= 8, WR >= 55%, MDD > -8%
Rank    : net_pct  (total return)
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings, itertools, csv
warnings.filterwarnings("ignore")

# ── Fixed params ───────────────────────────────────────────────────────────────
TICKER    = "CLM"; INTERVAL = "1h"; PERIOD = "max"
INIT_CAP  = 10_000.0; COMMISSION = 0.0006; RISK_PCT = 0.01
EMA_FAST  = 21; EMA_MID = 34; EMA_SLOW = 200
ADX_LEN   = 14; RSI_LEN = 20; ATR_LEN = 14; ATR_BL = 50; VOL_LEN = 20
VOL_MULT  = 1.2; PANIC_MULT = 1.4; ATR_FLOOR = 0.0; MIN_BODY = 0.05
RSI_LO_L  = 40; RSI_HI_L = 70; RSI_LO_S = 30; RSI_HI_S = 60
USE_SLOPE = False; TRAIL_DIST = 0.3

WARMUP = EMA_SLOW + 50

# ── Download ───────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} {PERIOD} …")
raw = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                  auto_adjust=True, progress=False)
raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
df = raw[["Open","High","Low","Close","Volume"]].copy().dropna()
df.index = pd.to_datetime(df.index)
print(f"  {len(df)} bars  {df.index[0].date()} → {df.index[-1].date()}")

# ── Indicators (precomputed once) ──────────────────────────────────────────────
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi_f(s, n):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
def atr_s(h, l, c, n):
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
def adx_s(h, l, c, n):
    up = h.diff(); dn = -l.diff()
    pdm = up.where((up>dn)&(up>0), 0.0); ndm = dn.where((dn>up)&(dn>0), 0.0)
    tr14= atr_s(h,l,c,n)
    pdi = 100*pdm.ewm(alpha=1/n,adjust=False).mean()/tr14.replace(0,np.nan)
    ndi = 100*ndm.ewm(alpha=1/n,adjust=False).mean()/tr14.replace(0,np.nan)
    dx  = 100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()

df["EMA_F"] = ema(df["Close"], EMA_FAST)
df["EMA_M"] = ema(df["Close"], EMA_MID)
df["EMA_S"] = ema(df["Close"], EMA_SLOW)
df["ATR"]   = atr_s(df["High"], df["Low"], df["Close"], ATR_LEN)
df["ATR_BL"]= df["ATR"].rolling(ATR_BL).mean()
df["ADX"]   = adx_s(df["High"], df["Low"], df["Close"], ADX_LEN)
df["RSI"]   = rsi_f(df["Close"], RSI_LEN)
df["VOL_MA"]= df["Volume"].rolling(VOL_LEN).mean()
df["BODY"]  = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, np.nan)
df["EMA_SL"]= df["EMA_F"] - df["EMA_F"].shift(3)
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

# Precompute fixed signal components (direction-independent)
vol_ok    = df["Volume"] >= df["VOL_MA"] * VOL_MULT
body_ok   = df["BODY"] >= MIN_BODY
ema_bull  = (df["EMA_F"] > df["EMA_M"]) & (df["Close"] > df["EMA_S"])
ema_bear  = (df["EMA_F"] < df["EMA_M"]) & (df["Close"] < df["EMA_S"])
rsi_long  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

o = df["Open"].values; h = df["High"].values
l = df["Low"].values;  c = df["Close"].values
atr_v  = df["ATR"].values; idx = df.index
COMM = COMMISSION

print(f"Indicators computed. Starting sweep …\n")

# ── Sweep axes ────────────────────────────────────────────────────────────────
TP_MULTS   = [2.0, 3.0, 5.0, 8.0, 12.0]
TRAIL_ACTS = [2.0, 3.0, 99.0]
ADX_THRS   = [15, 20, 25, 30]
PB_PCTS    = [0.10, 0.20, 0.40]
SL_MULTS   = [1.0, 1.5, 2.0]
DIRS       = [(True, False), (True, True)]   # (longs, shorts)

combos = list(itertools.product(TP_MULTS, TRAIL_ACTS, ADX_THRS, PB_PCTS, SL_MULTS, DIRS))
total  = len(combos)
print(f"Sweeping {total} combos …")

results = []
TRENDING_CACHE = {}   # cache ADX boolean per threshold

def get_trending(adx_thr):
    if adx_thr not in TRENDING_CACHE:
        TRENDING_CACHE[adx_thr] = (df["ADX"] > adx_thr).values
    return TRENDING_CACHE[adx_thr]

def get_signals(pb_pct, adx_thr, do_longs, do_shorts):
    pb_up = df["EMA_F"].shift(1) * (1.0 + pb_pct / 100.0)
    pb_dn = df["EMA_F"].shift(1) * (1.0 - pb_pct / 100.0)
    long_pb  = (df["Low"].shift(1) <= pb_up) & (df["Close"] > df["EMA_F"]) & \
               (df["Close"] > df["Open"]) & body_ok
    short_pb = (df["High"].shift(1) >= pb_dn) & (df["Close"] < df["EMA_F"]) & \
               (df["Close"] < df["Open"]) & body_ok
    trend = df["ADX"] > adx_thr
    ls = do_longs  and (long_pb  & ema_bull & rsi_long  & vol_ok & trend & ~is_panic)
    ss = do_shorts and (short_pb & ema_bear & rsi_short & vol_ok & trend & ~is_panic)
    le = ls.values if do_longs  else np.zeros(len(df), dtype=bool)
    se = ss.values if do_shorts else np.zeros(len(df), dtype=bool)
    return le, se

SIGNAL_CACHE = {}

for ci, (tp_m, tr_act, adx_thr, pb_pct, sl_m, (do_l, do_s)) in enumerate(combos):
    if ci % 100 == 0:
        print(f"  {ci}/{total} …", flush=True)

    # signals (cached per pb/adx/dirs)
    sig_key = (pb_pct, adx_thr, do_l, do_s)
    if sig_key not in SIGNAL_CACHE:
        SIGNAL_CACHE[sig_key] = get_signals(pb_pct, adx_thr, do_l, do_s)
    l_entry, s_entry = SIGNAL_CACHE[sig_key]

    # simulation
    equity = INIT_CAP; in_t = False; d = None
    ep = sl = tp = best = entry_atr = qty = 0.0
    wins = losses = 0
    eq_curve = [INIT_CAP]

    for i in range(WARMUP, len(df)):
        av = atr_v[i]
        if np.isnan(av) or av == 0: eq_curve.append(equity); continue

        if in_t:
            if d == "long":
                if h[i] > best: best = h[i]
                if best >= ep + entry_atr * tr_act:
                    new_sl = max(sl, best - entry_atr * TRAIL_DIST)
                    sl = new_sl
                hit_sl = l[i] <= sl; hit_tp = not hit_sl and h[i] >= tp
            else:
                if l[i] < best: best = l[i]
                if best <= ep - entry_atr * tr_act:
                    new_sl = min(sl, best + entry_atr * TRAIL_DIST)
                    sl = new_sl
                hit_sl = h[i] >= sl; hit_tp = not hit_sl and l[i] <= tp

            if hit_sl or hit_tp:
                xp_ = (tp if hit_tp else sl)
                if d == "long":
                    pnl = (xp_ - ep) * qty - (ep + xp_) * qty * COMM
                else:
                    pnl = (ep - xp_) * qty - (ep + xp_) * qty * COMM
                equity += pnl
                if pnl > 0: wins += 1
                else:        losses += 1
                in_t = False

        if not in_t:
            sig = "long" if l_entry[i] else ("short" if s_entry[i] else None)
            if sig:
                sd = av * sl_m; ep = c[i]
                sl = ep - sd if sig == "long" else ep + sd
                tp = ep + av * tp_m if sig == "long" else ep - av * tp_m
                best = ep; entry_atr = av; qty = equity * RISK_PCT / sd
                d = sig; in_t = True

        eq_curve.append(equity)

    total_t = wins + losses
    if total_t == 0: continue

    wr = wins / total_t * 100
    net_pct = (equity / INIT_CAP - 1) * 100
    eq_arr = np.array(eq_curve)
    rm = np.maximum.accumulate(eq_arr)
    mdd = ((eq_arr - rm) / rm * 100).min()

    if total_t < 8 or wr < 55 or mdd < -8:
        continue

    results.append({
        "tp_m": tp_m, "trail_act": tr_act, "adx": adx_thr,
        "pb_pct": pb_pct, "sl_m": sl_m,
        "longs": do_l, "shorts": do_s,
        "n": total_t, "wins": wins, "losses": losses,
        "wr": round(wr, 1), "net_pct": round(net_pct, 2),
        "mdd": round(mdd, 2),
        "calmar": round(net_pct / abs(mdd), 2) if mdd != 0 else 0,
    })

print(f"\nPassed filter: {len(results)} combos")
rdf = pd.DataFrame(results).sort_values("net_pct", ascending=False)
print(f"\nTop 20 by net return:")
print(rdf.head(20).to_string(index=False))

rdf.to_csv("sweep_apm_v5_1h_s1.csv", index=False)
print("\nSaved: sweep_apm_v5_1h_s1.csv")
