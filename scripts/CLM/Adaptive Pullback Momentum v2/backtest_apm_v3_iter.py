# ─────────────────────────────────────────────────────────────────────────────
# APM v2  —  v3 indicator iteration  (30m BTC-USD)
#
# BASELINE: v2.1 (previous session best: +9.48%, PF=2.297, WR=70%, 20 trades)
#
# NEW FILTERS UNDER TEST
#   A. DI directional alignment : DI+ > DI- for longs / DI- > DI+ for shorts
#      ADX only tells you a trend exists — DI alignment confirms it's in your
#      direction. Without this, you can enter a long while DI- dominates.
#   B. Strong close              : candle closes in upper ≥50% of its range
#      for longs (lower ≥50% for shorts). Filters weak recovery candles that
#      close near the middle or wrong end of the bar.
#   C. RSI 2-bar consecutive     : RSI rising on both current AND prior bar
#      for longs (falling both bars for shorts). Stronger momentum confirmation
#      than the current single-bar check.
#   D. ADX threshold sweep       : test 25 / 28 / 32 to find chop-filter sweet spot
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["yfinance", "pandas", "numpy", "matplotlib"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings("ignore")

# ─── Config ────────────────────────────────────────────────────────────────────
TICKER      = "BTC-USD"
PERIOD      = "max"
INTERVAL    = "30m"
INITIAL_CAP = 10_000.0
COMM        = 0.0006
RISK_PCT    = 0.01

# v2.1 confirmed best params (baseline)
PB_PCT     = 0.15
VOL_MULT   = 1.2
MIN_BODY   = 0.20
ATR_FLOOR  = 0.0020   # 0.20% — confirmed by extended sweep
SL_MULT    = 2.0
TP_MULT    = 3.0
TRAIL_ACT  = 2.5
TRAIL_DIST = 1.5
PANIC_MULT = 1.3
ADX_THRESH = 25
RSI_LO_L = 42;  RSI_HI_L = 68
RSI_LO_S = 32;  RSI_HI_S = 58

# ─── Download ──────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                 auto_adjust=True, progress=False)
df.columns = df.columns.get_level_values(0)
df.index   = pd.to_datetime(df.index, utc=True)
df.sort_index(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}\n")

# ─── Indicators ────────────────────────────────────────────────────────────────
def ema(s, n):  return s.ewm(span=n, adjust=False).mean()
def sma(s, n):  return s.rolling(n).mean()
def rsi_calc(s, n):
    d  = s.diff()
    g  = d.clip(lower=0).rolling(n).mean()
    ls = (-d).clip(lower=0).rolling(n).mean()
    return 100 - 100 / (1 + g / ls.replace(0, np.nan))
def atr_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()
def adx_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    up  = h.diff(); dn = -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr  = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    at  = tr.rolling(n).mean()
    pdi = pd.Series(pdm, index=h.index).rolling(n).mean() / at * 100
    ndi = pd.Series(ndm, index=h.index).rolling(n).mean() / at * 100
    dx  = ((pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan) * 100)
    return pdi, ndi, dx.rolling(n).mean()

df["EMA_FAST"] = ema(df["Close"], 21)
df["EMA_MID"]  = ema(df["Close"], 50)
df["EMA_SLOW"] = ema(df["Close"], 200)
df["RSI"]      = rsi_calc(df["Close"], 14)
df["ATR"]      = atr_calc(df, 14)
df["ATR_BL"]   = sma(df["ATR"], 60)
df["VOL_MA"]   = sma(df["Volume"], 20)
df["DI_PLUS"], df["DI_MINUS"], df["ADX"] = adx_calc(df, 14)
df.dropna(inplace=True)

# ─── v2.1 baseline filters (already confirmed) ─────────────────────────────────
pb_tol_up  = df["EMA_FAST"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - PB_PCT / 100.0)
body_size  = (df["Close"] - df["Open"]).abs() / df["ATR"]

long_pb  = (df["Low"].shift(1)  <= pb_tol_up) & (df["Close"] > df["EMA_FAST"]) & \
           (df["Close"] > df["Open"]) & (body_size >= MIN_BODY)
short_pb = (df["High"].shift(1) >= pb_tol_dn) & (df["Close"] < df["EMA_FAST"]) & \
           (df["Close"] < df["Open"]) & (body_size >= MIN_BODY)

ema_bull_full  = (df["EMA_FAST"] > df["EMA_MID"])  & (df["EMA_MID"]  > df["EMA_SLOW"])
ema_bear_full  = (df["EMA_FAST"] < df["EMA_MID"])  & (df["EMA_MID"]  < df["EMA_SLOW"])
ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
rsi_rising1    = df["RSI"] > df["RSI"].shift(1)     # single-bar (v2.1)
rsi_falling1   = df["RSI"] < df["RSI"].shift(1)
is_trending    = df["ADX"] > ADX_THRESH
is_panic       = df["ATR"] > df["ATR_BL"] * PANIC_MULT
vol_ok         = df["Volume"] >= df["VOL_MA"] * VOL_MULT
rsi_long_ok    = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok   = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
atr_pct_ok     = df["ATR"] / df["Close"] >= ATR_FLOOR

# v2.1 baseline signal
long_v21 = (long_pb & ema_bull_full & ema_slope_up & rsi_rising1 &
            rsi_long_ok & vol_ok & is_trending & ~is_panic & atr_pct_ok)
short_v21= (short_pb & ema_bear_full & ema_slope_down & rsi_falling1 &
            rsi_short_ok & vol_ok & is_trending & ~is_panic & atr_pct_ok)

# ─── NEW FILTER A: DI directional alignment ─────────────────────────────────────
# DI+ > DI- for longs: ADX trend is bullish-dominant
# DI- > DI+ for shorts: ADX trend is bearish-dominant
di_bull = df["DI_PLUS"]  > df["DI_MINUS"]
di_bear = df["DI_MINUS"] > df["DI_PLUS"]

# ─── NEW FILTER B: Strong close ─────────────────────────────────────────────────
# Bar range = high - low.  Close must be in upper half for longs, lower half for shorts.
# Guards against a candle that reverses mid-bar and closes near the bottom.
bar_range      = (df["High"] - df["Low"]).replace(0, np.nan)
close_pos      = (df["Close"] - df["Low"]) / bar_range   # 0=low end, 1=high end
strong_close_l = close_pos >= 0.50    # closes in upper half of candle
strong_close_s = close_pos <= 0.50    # closes in lower half of candle

# ─── NEW FILTER C: RSI 2-bar consecutive ────────────────────────────────────────
rsi_rising2  = rsi_rising1  & (df["RSI"].shift(1) > df["RSI"].shift(2))
rsi_falling2 = rsi_falling1 & (df["RSI"].shift(1) < df["RSI"].shift(2))

# ─── v3 combined signal ─────────────────────────────────────────────────────────
long_v3 = (long_pb & ema_bull_full & ema_slope_up &
           di_bull & strong_close_l & rsi_rising2 &
           rsi_long_ok & vol_ok & is_trending & ~is_panic & atr_pct_ok)
short_v3= (short_pb & ema_bear_full & ema_slope_down &
           di_bear & strong_close_s & rsi_falling2 &
           rsi_short_ok & vol_ok & is_trending & ~is_panic & atr_pct_ok)

# ─── Signal diagnostics ─────────────────────────────────────────────────────────
components_v3_long = [
    ("long_pb",        long_pb),
    ("ema_bull_full",  ema_bull_full),
    ("ema_slope_up",   ema_slope_up),
    ("di_bull",        di_bull),
    ("strong_close_l", strong_close_l),
    ("rsi_rising_2bar",rsi_rising2),
    ("rsi_long_ok",    rsi_long_ok),
    ("vol_ok",         vol_ok),
    ("is_trending",    is_trending),
    ("~is_panic",      ~is_panic),
    ("atr_pct_ok",     atr_pct_ok),
]
components_v3_short = [
    ("short_pb",       short_pb),
    ("ema_bear_full",  ema_bear_full),
    ("ema_slope_down", ema_slope_down),
    ("di_bear",        di_bear),
    ("strong_close_s", strong_close_s),
    ("rsi_fall_2bar",  rsi_falling2),
    ("rsi_short_ok",   rsi_short_ok),
    ("vol_ok",         vol_ok),
    ("is_trending",    is_trending),
    ("~is_panic",      ~is_panic),
    ("atr_pct_ok",     atr_pct_ok),
]
print("--- v3 Signal filter pass-through (long) ---")
cumulative = pd.Series([True]*len(df), index=df.index)
for name, mask in components_v3_long:
    cumulative = cumulative & mask
    print(f"  {name:<20} → {cumulative.sum():>4} rows pass")
print("--- v3 Signal filter pass-through (short) ---")
cumulative = pd.Series([True]*len(df), index=df.index)
for name, mask in components_v3_short:
    cumulative = cumulative & mask
    print(f"  {name:<20} → {cumulative.sum():>4} rows pass")
print(f"\nv3 Signals — Long: {long_v3.sum()}  Short: {short_v3.sum()}")

# ─── Simulation ────────────────────────────────────────────────────────────────
def run_sim(df, l_sig, s_sig, sl_m, tp_m, ta, td, rp=RISK_PCT, af=0.0, cap=INITIAL_CAP):
    eq  = cap
    pos = None
    trs = []
    eqc = []
    for ts, row in df.iterrows():
        cl = float(row["Close"]); hi = float(row["High"])
        lo = float(row["Low"]);   av = float(row["ATR"])
        htp = hsl = False
        xp = pnl = 0.0; d = None
        if pos is not None:
            d = pos["d"]
            if d == "long":
                if hi > pos["best"]: pos["best"] = hi
                if pos["best"] >= pos["tap"]:
                    pos["sl"] = max(pos["sl"], pos["best"] - pos["tdf"])
                htp = hi >= pos["tp"]; hsl = lo <= pos["sl"]
            else:
                if lo < pos["best"]: pos["best"] = lo
                if pos["best"] <= pos["tap"]:
                    pos["sl"] = min(pos["sl"], pos["best"] + pos["tdf"])
                htp = lo <= pos["tp"]; hsl = hi >= pos["sl"]
            if htp or hsl:
                xp  = pos["tp"] if htp else pos["sl"]
                pnl = ((xp-pos["e"])/pos["e"] if d=="long" else (pos["e"]-xp)/pos["e"])
        if htp or hsl:
            dp = pnl*pos["n"] - pos["n"]*COMM*2
            eq += dp
            trs.append({"entry_time":pos["et"],"exit_time":ts,"direction":d,
                        "entry":pos["e"],"exit":xp,
                        "result":"TP" if htp else "SL",
                        "pnl_pct":round(pnl*100,3),
                        "dollar_pnl":round(dp,2),"equity":round(eq,2)})
            pos = None
        if pos is None:
            sig = ("long" if bool(l_sig[ts]) else "short" if bool(s_sig[ts]) else None)
            if sig:
                if af > 0 and av/cl < af:
                    pass
                else:
                    sd  = av*sl_m
                    n   = min(eq*rp/sd*cl, eq*5.0)
                    sl  = cl-sd if sig=="long" else cl+sd
                    tp  = cl+av*tp_m if sig=="long" else cl-av*tp_m
                    tap = cl+av*ta if sig=="long" else cl-av*ta
                    pos = {"d":sig,"e":cl,"et":ts,"sl":sl,"tp":tp,
                           "best":cl,"n":n,"tap":tap,"tdf":av*td}
        eqc.append({"time":ts,"equity":eq})
    return pd.DataFrame(trs), eq, eqc

def stats(tdf, feq, label="", cap=INITIAL_CAP):
    if tdf.empty:
        print(f"  {label}: No trades."); return None
    w = tdf[tdf["dollar_pnl"]>0]; l = tdf[tdf["dollar_pnl"]<=0]
    wp  = len(w)/len(tdf)*100
    ret = (feq/cap-1)*100
    pf  = w["dollar_pnl"].sum()/abs(l["dollar_pnl"].sum()) if not l.empty and l["dollar_pnl"].sum()!=0 else float("inf")
    rr  = w["dollar_pnl"].mean()/abs(l["dollar_pnl"].mean()) if not l.empty else float("inf")
    pk  = cap; mdd = 0.0
    for e in tdf["equity"]:
        if e > pk: pk = e
        dd = (e-pk)/pk*100
        if dd < mdd: mdd = dd
    print()
    print("=" * 60)
    print(f"  {label}  —  {TICKER} {INTERVAL}")
    print("=" * 60)
    print(f"  Initial capital   :  $ {cap:>10,.2f}")
    print(f"  Final equity      :  $ {feq:>10,.2f}")
    print(f"  Net P&L           : $ {feq-cap:>+10,.2f}")
    print(f"  Return            :  {ret:>10.2f} %")
    print(f"  Max drawdown      :  {mdd:>10.2f} %")
    print(f"  Profit factor     :  {pf:>10.3f}")
    print("-" * 60)
    print(f"  Total trades      : {len(tdf):>6}")
    print(f"    Long  trades    : {(tdf['direction']=='long').sum():>6}")
    print(f"    Short trades    : {(tdf['direction']=='short').sum():>6}")
    print(f"  TP exits          : {(tdf['result']=='TP').sum():>6}")
    print(f"  SL exits          : {(tdf['result']=='SL').sum():>6}")
    print(f"  Win rate          :  {wp:>10.1f} %")
    print(f"  Avg win           :  $ {w['dollar_pnl'].mean():>+9.2f}")
    print(f"  Avg loss          :  $ {l['dollar_pnl'].mean():>+9.2f}" if not l.empty else "  Avg loss          :       n/a")
    print(f"  Avg R:R           :  {rr:>10.2f}")
    print(f"  Best trade        :  $ {tdf['dollar_pnl'].max():>+9.2f}")
    print(f"  Worst trade       :  $ {tdf['dollar_pnl'].min():>+9.2f}")
    print("=" * 60)
    for d in ["long","short"]:
        sub = tdf[tdf["direction"]==d]
        if sub.empty: continue
        sw = sub[sub["dollar_pnl"]>0]; sl = sub[sub["dollar_pnl"]<=0]
        sub_wr = len(sw)/len(sub)*100
        sub_pf = sw["dollar_pnl"].sum()/abs(sl["dollar_pnl"].sum()) if not sl.empty and sl["dollar_pnl"].sum()!=0 else float("inf")
        print(f"  {d.upper():<6} trades={len(sub):>3}  WR={sub_wr:.0f}%  PF={sub_pf:.3f}  net=${sub['dollar_pnl'].sum():+.2f}")
    return ret, pf, wp, mdd

# ─── Head-to-head: v2.1 vs v3 at confirmed best params ──────────────────────────
print("\n" + "="*60)
print("  HEAD-TO-HEAD: v2.1  vs  v3  (TP×3.0 SL×2.0 ATRf=0.20%)")
print("="*60)
t21, eq21, _ = run_sim(df, long_v21, short_v21, SL_MULT, TP_MULT, TRAIL_ACT, TRAIL_DIST, af=ATR_FLOOR)
r21 = stats(t21, eq21, f"v2.1 baseline (TP×{TP_MULT} SL×{SL_MULT})")

t3, eq3, _ = run_sim(df, long_v3, short_v3, SL_MULT, TP_MULT, TRAIL_ACT, TRAIL_DIST, af=ATR_FLOOR)
r3 = stats(t3, eq3, f"v3 new filters (TP×{TP_MULT} SL×{SL_MULT})")

# ─── Sweep: test each new filter individually to isolate value ──────────────────
print("\n=== Filter isolation: which new filter adds most value? ===")
print(f"  {'Label':<28} | {'Trades':>6} {'WR%':>6} {'PF':>7} {'Ret%':>8}")
print("  " + "-"*58)

candidates = [
    ("v2.1 baseline",          long_v21, short_v21),
    ("+ DI alignment",
        long_v21  & di_bull,
        short_v21 & di_bear),
    ("+ strong close",
        long_v21  & strong_close_l,
        short_v21 & strong_close_s),
    ("+ RSI 2-bar",
        long_v21  & rsi_rising2,
        short_v21 & rsi_falling2),
    ("+ all three (v3)",        long_v3, short_v3),
    ("+ DI + strong close",
        long_v21  & di_bull & strong_close_l,
        short_v21 & di_bear & strong_close_s),
    ("+ DI + RSI 2-bar",
        long_v21  & di_bull & rsi_rising2,
        short_v21 & di_bear & rsi_falling2),
    ("+ strong close + RSI 2",
        long_v21  & strong_close_l & rsi_rising2,
        short_v21 & strong_close_s & rsi_falling2),
]

iso_rows = []
for label, ls, ss in candidates:
    t, eq, _ = run_sim(df, ls, ss, SL_MULT, TP_MULT, TRAIL_ACT, TRAIL_DIST, af=ATR_FLOOR)
    if t.empty:
        print(f"  {label:<28} | no trades")
        continue
    w = t[t["dollar_pnl"]>0]; l = t[t["dollar_pnl"]<=0]
    wr_  = len(w)/len(t)*100
    ret_ = (eq/INITIAL_CAP-1)*100
    pf_  = (w["dollar_pnl"].sum()/abs(l["dollar_pnl"].sum())
            if not l.empty and l["dollar_pnl"].sum()!=0 else float("inf"))
    iso_rows.append({"label":label,"trades":len(t),"wr":wr_,"pf":pf_,"ret":ret_,"ls":ls,"ss":ss})
    marker = " ←" if ret_ > (iso_rows[0]["ret"] if iso_rows else 0) else ""
    print(f"  {label:<28} | {len(t):>6} {wr_:>6.1f} {pf_:>7.3f} {ret_:>8.2f}%{marker}")

# ─── Full sweep with best v3 signal set ─────────────────────────────────────────
print("\n=== Full sweep: best v3 filter combo × TP × SL × ADX ===")
print(f"{'ADX':>5} {'TP':>5} {'SL':>5} | {'Trades':>6} {'WR%':>6} {'PF':>7} {'Ret%':>8}")
print("-" * 55)

adx_vals = [25, 28, 32]
tp_vals  = [2.5, 3.0, 3.5]
sl_vals  = [1.5, 2.0, 2.5]

# pick best combo from isolation test
best_iso = max(iso_rows, key=lambda x: x["ret"]) if iso_rows else {"ls": long_v3, "ss": short_v3}
best_ls, best_ss_base = best_iso["ls"], best_iso["ss"]
print(f"  Using signal set: '{best_iso['label']}'")

sweep_rows = []
for adx_t in adx_vals:
    is_trend_sw = df["ADX"] > adx_t
    # re-apply is_trending with new threshold to the best filter combo
    # (rebuild signal with updated is_trending — strip old is_trending first is complex,
    #  instead compute from scratch with the best component masks)
    if best_iso["label"] == "v2.1 baseline":
        ls_sw = (long_pb & ema_bull_full & ema_slope_up & rsi_rising1 &
                 rsi_long_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
        ss_sw = (short_pb & ema_bear_full & ema_slope_down & rsi_falling1 &
                 rsi_short_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
    elif "+ DI + strong close" in best_iso["label"]:
        ls_sw = (long_pb & ema_bull_full & ema_slope_up & di_bull & strong_close_l &
                 rsi_rising1 & rsi_long_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
        ss_sw = (short_pb & ema_bear_full & ema_slope_down & di_bear & strong_close_s &
                 rsi_falling1 & rsi_short_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
    elif "+ DI + RSI 2-bar" in best_iso["label"]:
        ls_sw = (long_pb & ema_bull_full & ema_slope_up & di_bull & rsi_rising2 &
                 rsi_long_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
        ss_sw = (short_pb & ema_bear_full & ema_slope_down & di_bear & rsi_falling2 &
                 rsi_short_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
    elif "+ strong close + RSI 2" in best_iso["label"]:
        ls_sw = (long_pb & ema_bull_full & ema_slope_up & strong_close_l & rsi_rising2 &
                 rsi_long_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
        ss_sw = (short_pb & ema_bear_full & ema_slope_down & strong_close_s & rsi_falling2 &
                 rsi_short_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
    elif "all three" in best_iso["label"] or "v3" in best_iso["label"]:
        ls_sw = (long_pb & ema_bull_full & ema_slope_up & di_bull & strong_close_l &
                 rsi_rising2 & rsi_long_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
        ss_sw = (short_pb & ema_bear_full & ema_slope_down & di_bear & strong_close_s &
                 rsi_falling2 & rsi_short_ok & vol_ok & is_trend_sw & ~is_panic & atr_pct_ok)
    else:
        # default fallback: v3 full
        ls_sw = long_v3 & is_trend_sw & ~is_panic  # rough re-filter (ADX already in v3)
        ss_sw = short_v3 & is_trend_sw & ~is_panic

    for tp_m in tp_vals:
        for sl_m in sl_vals:
            t, eq, _ = run_sim(df, ls_sw, ss_sw, sl_m, tp_m, TRAIL_ACT, TRAIL_DIST, af=ATR_FLOOR)
            if t.empty: continue
            w = t[t["dollar_pnl"]>0]; l = t[t["dollar_pnl"]<=0]
            wr_  = len(w)/len(t)*100
            ret_ = (eq/INITIAL_CAP-1)*100
            pf_  = (w["dollar_pnl"].sum()/abs(l["dollar_pnl"].sum())
                    if not l.empty and l["dollar_pnl"].sum()!=0 else float("inf"))
            sweep_rows.append({"adx":adx_t,"tp":tp_m,"sl":sl_m,
                               "trades":len(t),"wr":wr_,"pf":pf_,"ret":ret_,
                               "ls":ls_sw,"ss":ss_sw})
            marker = " ←" if ret_ >= 9.48 else ""  # v2.1 best was 9.48
            print(f"{adx_t:>5} {tp_m:>5.1f} {sl_m:>5.1f} | "
                  f"{len(t):>6} {wr_:>6.1f} {pf_:>7.3f} {ret_:>8.2f}%{marker}")

if sweep_rows:
    best = max(sweep_rows, key=lambda x: x["ret"])
    bestPF = max(sweep_rows, key=lambda x: x["pf"])
    print(f"\nBest Ret : ADX>{best['adx']} TP×{best['tp']} SL×{best['sl']} → "
          f"{best['ret']:+.2f}%  PF={best['pf']:.3f}  WR={best['wr']:.1f}%  Trades={best['trades']}")
    print(f"Best PF  : ADX>{bestPF['adx']} TP×{bestPF['tp']} SL×{bestPF['sl']} → "
          f"PF={bestPF['pf']:.3f}  Ret={bestPF['ret']:+.2f}%  WR={bestPF['wr']:.1f}%  Trades={bestPF['trades']}")

    # ─── Final confirmed run ──────────────────────────────────────────────────
    b = best
    print(f"\n--- Final confirmed run: ADX>{b['adx']} TP×{b['tp']} SL×{b['sl']} ---")
    t_f, eq_f, eqc_f = run_sim(df, b["ls"], b["ss"], b["sl"], b["tp"],
                                 TRAIL_ACT, TRAIL_DIST, af=ATR_FLOOR)
    r_f = stats(t_f, eq_f, f"APM v3 Final  ADX>{b['adx']} TP×{b['tp']} SL×{b['sl']}")

    if r_f is not None:
        ret_f, pf_f, wr_f, mdd_f = r_f

        # save outputs
        out_csv = f"apm_v3_trades_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
        t_f.to_csv(out_csv, index=False)
        print(f"Trades CSV → {out_csv}")

        eq_df = pd.DataFrame(eqc_f).set_index("time")
        fig, axes = plt.subplots(2, 1, figsize=(14, 8),
                                  gridspec_kw={"height_ratios": [3, 1]})
        ax1, ax2 = axes
        ax1.plot(eq_df.index, eq_df["equity"], color="#63b3ed", linewidth=1.5)
        ax1.axhline(INITIAL_CAP, color="#718096", linewidth=0.8, linestyle="--", alpha=0.7)
        ax1.fill_between(eq_df.index, eq_df["equity"], INITIAL_CAP,
                         where=eq_df["equity"] >= INITIAL_CAP, alpha=0.15, color="#48bb78")
        ax1.fill_between(eq_df.index, eq_df["equity"], INITIAL_CAP,
                         where=eq_df["equity"] <  INITIAL_CAP, alpha=0.15, color="#fc8181")
        for _, tr in t_f.iterrows():
            ax1.axvline(tr["exit_time"], alpha=0.2,
                        color="#48bb78" if tr["dollar_pnl"]>0 else "#fc8181", linewidth=0.6)
        eq_s = pd.Series([e["equity"] for e in eqc_f])
        dd   = (eq_s - eq_s.cummax()) / eq_s.cummax() * 100
        ax2.fill_between(eq_df.index, dd.values, 0, color="#fc8181", alpha=0.6)
        ax2.set_ylabel("Drawdown %")
        ax2.set_ylim(min(dd.min()*1.1, -0.5), 1)
        color_r = "#48bb78" if ret_f >= 0 else "#fc8181"
        ax1.set_title(
            f"APM v3  |  {TICKER} {INTERVAL}  |  "
            f"Return: {ret_f:+.2f}%  PF: {pf_f:.3f}  WR: {wr_f:.1f}%  "
            f"Trades: {len(t_f)}  MaxDD: {mdd_f:.2f}%",
            color=color_r, fontsize=11)
        ax1.set_ylabel("Equity ($)")
        for ax in [ax1, ax2]:
            ax.set_facecolor("#0d0d1a"); ax.tick_params(colors="#718096")
            ax.yaxis.label.set_color("#718096")
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            for spine in ax.spines.values(): spine.set_edgecolor("#2d3748")
        ax1.title.set_color(color_r)
        fig.patch.set_facecolor("#0d0d1a")
        fig.autofmt_xdate()
        plt.tight_layout()
        out_png = f"apm_v3_equity_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
        plt.savefig(out_png, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Chart → {out_png}")

        print(f"\n>>> BEST CONFIG FOR PINE SCRIPT UPDATE <<<")
        print(f"  ADX_THRESH = {b['adx']}")
        print(f"  SL_MULT    = {b['sl']}")
        print(f"  TP_MULT    = {b['tp']}")
        print(f"  ATR_FLOOR  = 0.20%")
        print(f"  VOL_MULT   = {VOL_MULT}")
        print(f"  MIN_BODY   = {MIN_BODY}")
        print(f"  TRAIL_ACT  = {TRAIL_ACT}")
        print(f"  TRAIL_DIST = {TRAIL_DIST}")
        print(f"  Filter set : {best_iso['label']}")
