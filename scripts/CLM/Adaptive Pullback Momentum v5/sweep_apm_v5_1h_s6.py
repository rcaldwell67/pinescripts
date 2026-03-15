"""
sweep_apm_v5_1h_s6.py — APM v5 CLM 1h  Stage-6: Risk% + Signal expansion
==========================================================================
Goal : Push net profit above 20%.

S5 finding : SL=0.9, TRAIL_ACT=2.0, TRAIL_DIST=0.5 is the per-trade optimum.
             SL=0.7 is filtered out (WR collapses).
             Primary untested levers are risk% and signal volume.

Two axes of exploration
  (A) Risk% scaling         — same 13-trade quality, larger position per trade
  (B) Signal count          — relax ADX/PB/VOL to generate more trades
  (C) Fine SL around 0.9   — tiny step inside the proven window

Axes:
  RISK_PCT   : 1.0, 1.25, 1.5, 1.75, 2.0
  ADX_THRESH : 25, 28, 30, 33
  SL_MULT    : 0.8, 0.9, 1.0
  PB_PCT     : 0.20, 0.30, 0.50
  VOL_MULT   : 1.0, 1.2

Fixed: TRAIL_ACT=2.0, TRAIL_DIST=0.5, TP=10.0, MIN_BODY=0.05
       EMA 21/34/200, RSI 20, ATR 14, ATR_BL 50, PANIC 1.4
       Longs + Shorts

Total: 5×4×3×3×2 = 360 combos
Filter: n >= 8, WR >= 55%, Calmar >= 1.5   (MDD filter removed — risk% scaling)
Rank: net_pct
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings, itertools
warnings.filterwarnings("ignore")

TICKER = "CLM"; INTERVAL = "1h"; PERIOD = "max"
INIT_CAP   = 10_000.0
COMMISSION = 0.0006

# Fixed params
EMA_FAST   = 21;  EMA_MID   = 34;  EMA_SLOW  = 200
ADX_LEN    = 14;  RSI_LEN   = 20;  ATR_LEN   = 14
ATR_BL     = 50;  VOL_LEN   = 20
PANIC_MULT = 1.4; ATR_FLOOR = 0.0; MIN_BODY  = 0.05
RSI_LO_L   = 40;  RSI_HI_L  = 70
RSI_LO_S   = 30;  RSI_HI_S  = 60
DO_LONGS   = True; DO_SHORTS = True
TRAIL_ACT  = 2.0; TRAIL_DIST = 0.5; TP_MULT  = 10.0
WARMUP     = EMA_SLOW + 50

print(f"Downloading {TICKER} {INTERVAL} {PERIOD} …")
raw = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                  auto_adjust=True, progress=False)
raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
df = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()
df.index = pd.to_datetime(df.index)
print(f"  {len(df)} bars  {df.index[0].date()} → {df.index[-1].date()}")

def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rsi_f(s, n):
    d  = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def atr_s(h, l, c, n):
    tr = pd.concat([h - l,
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def adx_s(h, l, c, n):
    up  = h.diff(); dn = -l.diff()
    pdm = up.where((up > dn) & (up > 0),  0.0)
    ndm = dn.where((dn > up) & (dn > 0),  0.0)
    tr  = atr_s(h, l, c, n)
    pdi = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / tr.replace(0, np.nan)
    ndi = 100 * ndm.ewm(alpha=1/n, adjust=False).mean() / tr.replace(0, np.nan)
    dx  = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()

df["EMA_F"]  = ema(df["Close"], EMA_FAST)
df["EMA_M"]  = ema(df["Close"], EMA_MID)
df["EMA_S"]  = ema(df["Close"], EMA_SLOW)
df["ATR"]    = atr_s(df["High"], df["Low"], df["Close"], ATR_LEN)
df["ATR_BL"] = df["ATR"].rolling(ATR_BL).mean()
df["ADX"]    = adx_s(df["High"], df["Low"], df["Close"], ADX_LEN)
df["RSI"]    = rsi_f(df["Close"], RSI_LEN)
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()
is_panic     = (df["ATR"] > df["ATR_BL"] * PANIC_MULT)

ema_bull  = (df["EMA_F"] > df["EMA_M"]) & (df["Close"] > df["EMA_S"])
ema_bear  = (df["EMA_F"] < df["EMA_M"]) & (df["Close"] < df["EMA_S"])
rsi_long  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
body_len  = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, np.nan)
body_ok   = body_len >= MIN_BODY

o = df["Open"].values;  h = df["High"].values
l = df["Low"].values;   c = df["Close"].values
atr_v = df["ATR"].values

print("Indicators computed. Starting sweep …\n")

# ── Sweep axes ─────────────────────────────────────────────────────────────────
RISK_PCTS   = [1.0, 1.25, 1.5, 1.75, 2.0]
ADX_THRS    = [25, 28, 30, 33]
SL_MULTS    = [0.8, 0.9, 1.0]
PB_PCTS     = [0.20, 0.30, 0.50]
VOL_MULTS   = [1.0, 1.2]

combos = list(itertools.product(RISK_PCTS, ADX_THRS, SL_MULTS, PB_PCTS, VOL_MULTS))
total  = len(combos)
print(f"Sweeping {total} combos …")

# Pre-build ADX×PB×VOL signal cache
SIGNAL_CACHE = {}
results = []

for ci, (risk_pct, adx_thr, sl_m, pb_pct, vol_mult) in enumerate(combos):
    if ci % 72 == 0:
        print(f"  {ci}/{total} …", flush=True)

    key = (adx_thr, pb_pct, vol_mult)
    if key not in SIGNAL_CACHE:
        trend  = df["ADX"] > adx_thr
        vol_ok = df["Volume"] >= df["VOL_MA"] * vol_mult
        pb_up  = df["EMA_F"].shift(1) * (1.0 + pb_pct / 100.0)
        pb_dn  = df["EMA_F"].shift(1) * (1.0 - pb_pct / 100.0)
        long_pb  = (df["Low"].shift(1)  <= pb_up) & \
                   (df["Close"] > df["EMA_F"]) & \
                   (df["Close"] > df["Open"]) & body_ok
        short_pb = (df["High"].shift(1) >= pb_dn) & \
                   (df["Close"] < df["EMA_F"]) & \
                   (df["Close"] < df["Open"]) & body_ok
        le = (long_pb  & ema_bull & rsi_long  & vol_ok & trend & ~is_panic).values
        se = (short_pb & ema_bear & rsi_short & vol_ok & trend & ~is_panic).values
        SIGNAL_CACHE[key] = (le, se)

    l_entry, s_entry = SIGNAL_CACHE[key]
    RISK  = risk_pct / 100.0

    equity = INIT_CAP; in_t = False; d = None
    ep = sl = tp = best = entry_atr = qty = 0.0
    pending_sl = None
    wins = losses = tp_exits = sl_exits = trail_exits = 0
    eq_curve = [INIT_CAP]

    for i in range(WARMUP, len(df)):
        av = atr_v[i]
        if np.isnan(av) or av == 0:
            eq_curve.append(equity); continue

        if in_t:
            # Apply pending trail SL from previous bar (next-bar model)
            if pending_sl is not None:
                sl = pending_sl
                pending_sl = None

            if d == "long":
                if h[i] > best:
                    best = h[i]
                # Queue trail update (applied next bar)
                if best >= ep + entry_atr * TRAIL_ACT:
                    new_sl = best - entry_atr * TRAIL_DIST
                    if new_sl > sl and (pending_sl is None or new_sl > pending_sl):
                        pending_sl = new_sl

                hit_sl = l[i] <= sl
                hit_tp = (not hit_sl) and h[i] >= tp
                if hit_sl:
                    xp_  = min(o[i], sl)
                    pnl  = (xp_ - ep) * qty - (ep + xp_) * qty * COMMISSION
                    if pnl >= 0: trail_exits += 1
                    else:        sl_exits   += 1
                elif hit_tp:
                    xp_ = max(o[i], tp)
                    pnl = (xp_ - ep) * qty - (ep + xp_) * qty * COMMISSION
                    tp_exits += 1
                else:
                    eq_curve.append(equity); continue

            else:  # short
                if l[i] < best:
                    best = l[i]
                if best <= ep - entry_atr * TRAIL_ACT:
                    new_sl = best + entry_atr * TRAIL_DIST
                    if new_sl < sl and (pending_sl is None or new_sl < pending_sl):
                        pending_sl = new_sl

                hit_sl = h[i] >= sl
                hit_tp = (not hit_sl) and l[i] <= tp
                if hit_sl:
                    xp_ = max(o[i], sl)
                    pnl = (ep - xp_) * qty - (ep + xp_) * qty * COMMISSION
                    if pnl >= 0: trail_exits += 1
                    else:        sl_exits   += 1
                elif hit_tp:
                    xp_ = min(o[i], tp)
                    pnl = (ep - xp_) * qty - (ep + xp_) * qty * COMMISSION
                    tp_exits += 1
                else:
                    eq_curve.append(equity); continue

            equity += pnl
            if pnl >= 0: wins  += 1
            else:         losses += 1
            in_t = False; pending_sl = None

        if not in_t:
            sig = "long" if l_entry[i] else ("short" if s_entry[i] else None)
            if sig:
                sd = av * sl_m; ep = c[i]
                sl = ep - sd if sig == "long" else ep + sd
                tp = ep + av * TP_MULT if sig == "long" else ep - av * TP_MULT
                best = ep; entry_atr = av
                qty  = equity * RISK / sd
                d = sig; in_t = True; pending_sl = None

        eq_curve.append(equity)

    total_t = wins + losses
    if total_t == 0:
        continue
    wr      = wins / total_t * 100
    net_pct = (equity / INIT_CAP - 1) * 100
    eq_arr  = np.array(eq_curve)
    rm      = np.maximum.accumulate(eq_arr)
    mdd     = ((eq_arr - rm) / rm * 100).min()
    calmar  = round(net_pct / abs(mdd), 2) if mdd != 0 else 0

    # Filter: meaningful sample, acceptable quality, positive Calmar
    if total_t < 8 or wr < 55 or calmar < 1.5:
        continue

    results.append({
        "risk_pct":   risk_pct,
        "adx":        adx_thr,
        "sl_m":       sl_m,
        "pb_pct":     pb_pct,
        "vol_mult":   vol_mult,
        "n":          total_t,
        "wins":       wins,
        "losses":     losses,
        "tp_x":       tp_exits,
        "trail_x":    trail_exits,
        "sl_x":       sl_exits,
        "wr":         round(wr, 1),
        "net_pct":    round(net_pct, 2),
        "mdd":        round(mdd, 2),
        "calmar":     calmar,
    })

print(f"\nPassed filter: {len(results)} combos")
rdf = pd.DataFrame(results).sort_values("net_pct", ascending=False)

print("\nTop 25 by net return:")
print(rdf.head(25).to_string(index=False))
print()
print("Top 15 by Calmar (n>=10):")
print(rdf[rdf["n"] >= 10].sort_values("calmar", ascending=False).head(15).to_string(index=False))

rdf.to_csv("sweep_apm_v5_1h_s6.csv", index=False)
print("\nSaved: sweep_apm_v5_1h_s6.csv")
