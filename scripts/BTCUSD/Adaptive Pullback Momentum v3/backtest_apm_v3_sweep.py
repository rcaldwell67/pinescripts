# APM v3  —  15m indicator improvement sweep
#
# PROBLEM WITH v3.2 ON 15m
#   • TP×3.5 hit only 5/30 times — target too wide for 15m bars
#   • Longs: WR=36%, PF=0.313 — long side destroys returns
#   • Shorts: WR=63%, PF=1.065 — short side marginally profitable
#
# STRATEGY: sweep TP×SL×ADX×direction to find 15m-optimal config,
#   then test targeted filter additions on the best base config.

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

# ── Config ────────────────────────────────────────────────────────────────────
TICKER      = "BTC-USD"
PERIOD      = "max"
INTERVAL    = "15m"
INITIAL_CAP = 10_000.0
COMM        = 0.0006
RISK_PCT    = 0.03

# v3.2 baseline params
PB_PCT      = 0.15
VOL_MULT    = 1.2
MIN_BODY    = 0.20
ATR_FLOOR   = 0.0020
ADX_THRESH  = 25
RSI_LO_L = 42;  RSI_HI_L = 68
RSI_LO_S = 32;  RSI_HI_S = 58

# ── Download ──────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} ...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                 auto_adjust=True, progress=False)
df.columns = df.columns.get_level_values(0)
df.index   = pd.to_datetime(df.index, utc=True)
df.sort_index(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} -> {df.index[-1]}\n")

# ── Indicators ────────────────────────────────────────────────────────────────
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

# ── Base filters (v3.2 entry conditions, ADX threshold swept separately) ──────
pb_tol_up  = df["EMA_FAST"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - PB_PCT / 100.0)
body_size  = (df["Close"] - df["Open"]).abs() / df["ATR"]

long_pb  = (df["Low"].shift(1)  <= pb_tol_up) & (df["Close"] > df["EMA_FAST"]) & \
           (df["Close"] > df["Open"]) & (body_size >= MIN_BODY)
short_pb = (df["High"].shift(1) >= pb_tol_dn) & (df["Close"] < df["EMA_FAST"]) & \
           (df["Close"] < df["Open"]) & (body_size >= MIN_BODY)

ema_bull   = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"]  > df["EMA_SLOW"])
ema_bear   = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"]  < df["EMA_SLOW"])
slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
rsi_up     = df["RSI"] > df["RSI"].shift(1)
rsi_dn     = df["RSI"] < df["RSI"].shift(1)
vol_ok     = df["Volume"] >= df["VOL_MA"] * VOL_MULT
atr_ok_20  = df["ATR"] / df["Close"] >= 0.0020
atr_ok_15  = df["ATR"] / df["Close"] >= 0.0015
atr_ok_25  = df["ATR"] / df["Close"] >= 0.0025

# Pre-compute is_panic (fixed)
is_panic   = df["ATR"] > df["ATR_BL"] * 1.3

# ── Simulation helper ─────────────────────────────────────────────────────────
def run_sim(df, l_sig, s_sig, sl_m, tp_m, trail_act, trail_dist,
            af=0.0, cap=INITIAL_CAP):
    eq  = cap
    pos = None
    trs = []
    eqc = []
    for ts, row in df.iterrows():
        cl = float(row["Close"]); hi = float(row["High"])
        lo = float(row["Low"]);   av = float(row["ATR"])
        hit_tp = hit_sl = False
        if pos is not None:
            d = pos["d"]
            if d == "long":
                if hi > pos["best"]: pos["best"] = hi
                if pos["best"] >= pos["tap"]:
                    pos["sl"] = max(pos["sl"], pos["best"] - av * trail_dist)
                hit_tp = hi >= pos["tp"]; hit_sl = lo <= pos["sl"]
            else:
                if lo < pos["best"]: pos["best"] = lo
                if pos["best"] <= pos["tap"]:
                    pos["sl"] = min(pos["sl"], pos["best"] + av * trail_dist)
                hit_tp = lo <= pos["tp"]; hit_sl = hi >= pos["sl"]
        xp = pnl = 0.0
        if hit_tp or hit_sl:
            xp  = pos["tp"] if hit_tp else pos["sl"]
            d   = pos["d"]
            pnl = ((xp-pos["e"])/pos["e"] if d=="long" else (pos["e"]-xp)/pos["e"])
            dp  = pnl*pos["n"] - pos["n"]*COMM*2
            eq += dp
            trs.append({"entry_time":pos["et"],"exit_time":ts,"direction":d,
                        "entry":pos["e"],"exit":xp,
                        "result":"TP" if hit_tp else "SL",
                        "pnl_pct":round(pnl*100,3),
                        "dollar_pnl":round(dp,2),"equity":round(eq,2)})
            pos = None
        if pos is None:
            sig = ("long" if bool(l_sig[ts]) else "short" if bool(s_sig[ts]) else None)
            if sig:
                if af > 0 and av/cl < af:
                    pass
                else:
                    sd  = av * sl_m
                    n   = min(eq*RISK_PCT/sd*cl, eq*5.0)
                    sl  = cl-sd if sig=="long" else cl+sd
                    tp  = cl+av*tp_m if sig=="long" else cl-av*tp_m
                    tap = cl+av*trail_act if sig=="long" else cl-av*trail_act
                    pos = {"d":sig,"e":cl,"et":ts,"sl":sl,"tp":tp,
                           "best":cl,"n":n,"tap":tap}
        eqc.append({"time":ts,"equity":eq})
    return pd.DataFrame(trs), eq, eqc

def quick_stats(tdf, eq, cap=INITIAL_CAP):
    if tdf.empty: return None, None, None, None
    w = tdf[tdf["dollar_pnl"]>0]; l = tdf[tdf["dollar_pnl"]<=0]
    wr  = len(w)/len(tdf)*100
    ret = (eq/cap-1)*100
    pf  = (w["dollar_pnl"].sum()/abs(l["dollar_pnl"].sum())
           if not l.empty and l["dollar_pnl"].sum()!=0 else float("inf"))
    pk = cap; mdd = 0.0
    for e in tdf["equity"]:
        if e > pk: pk = e
        dd = (e-pk)/pk*100
        if dd < mdd: mdd = dd
    return ret, pf, wr, mdd

# ── PHASE 1: Direction isolation at v3.2 params ───────────────────────────────
print("=== PHASE 1: Direction isolation (v3.2 params TP=3.5 SL=2.0) ===")
adx_25 = df["ADX"] > 25
l12 = ~is_panic & adx_25 & long_pb  & ema_bull & slope_up   & rsi_up & rsi_up & vol_ok & atr_ok_20 & \
      (df["RSI"]>=RSI_LO_L) & (df["RSI"]<=RSI_HI_L)
s12 = ~is_panic & adx_25 & short_pb & ema_bear & slope_down & rsi_dn & rsi_dn & vol_ok & atr_ok_20 & \
      (df["RSI"]>=RSI_LO_S) & (df["RSI"]<=RSI_HI_S)

FALSE = pd.Series(False, index=df.index)
for label, ls, ss in [
    ("BOTH",         l12, s12),
    ("LONGS ONLY",   l12, FALSE),
    ("SHORTS ONLY",  FALSE, s12),
]:
    t, eq, _ = run_sim(df, ls, ss, 2.0, 3.5, 2.5, 1.5, af=0.0020)
    ret, pf, wr, mdd = quick_stats(t, eq)
    n = len(t) if not t.empty else 0
    print(f"  {label:<14} trades={n:>3}  WR={wr or 0:.1f}%  PF={pf or 0:.3f}  "
          f"Ret={ret or 0:+.2f}%  MaxDD={mdd or 0:.2f}%")

# ── PHASE 2: TP x SL sweep with SHORTS ONLY (15m short bias confirmed) ────────
print("\n=== PHASE 2: TP x SL sweep — SHORTS ONLY (ADX>25, ATRf=0.20%) ===")
print(f"  {'TP':>5} {'SL':>5} | {'Trades':>6} {'WR%':>6} {'PF':>7} {'Ret%':>8} {'MaxDD':>7}")
print("  " + "-"*52)

tp_vals   = [1.5, 2.0, 2.5, 3.0, 3.5]
sl_vals   = [1.0, 1.5, 2.0]
sweep1    = []
for tp_m in tp_vals:
    for sl_m in sl_vals:
        t, eq, _ = run_sim(df, FALSE, s12, sl_m, tp_m, 2.5, 1.5, af=0.0020)
        ret, pf, wr, mdd = quick_stats(t, eq)
        if ret is None: continue
        sweep1.append({"tp":tp_m,"sl":sl_m,"trades":len(t),"wr":wr,"pf":pf,"ret":ret,"mdd":mdd})
        mk = " <-" if ret >= 0 else ""
        print(f"  {tp_m:>5.1f} {sl_m:>5.1f} | {len(t):>6} {wr:>6.1f} {pf:>7.3f} {ret:>8.2f}% {mdd:>7.2f}%{mk}")

print()
if sweep1:
    best1 = max(sweep1, key=lambda x: x["ret"])
    print(f"  Best Ret: TP={best1['tp']} SL={best1['sl']} -> {best1['ret']:+.2f}% PF={best1['pf']:.3f} WR={best1['wr']:.1f}% Trades={best1['trades']}")

# ── PHASE 3: ADX threshold sweep at best TP/SL ────────────────────────────────
best_tp = best1["tp"] if sweep1 else 2.0
best_sl = best1["sl"] if sweep1 else 1.5
print(f"\n=== PHASE 3: ADX threshold sweep (Shorts only, TP={best_tp} SL={best_sl}) ===")
print(f"  {'ADX':>5} {'ATRf':>6} | {'Trades':>6} {'WR%':>6} {'PF':>7} {'Ret%':>8} {'MaxDD':>7}")
print("  " + "-"*54)

adx_vals  = [22, 25, 28, 32, 35]
atrf_vals = [0.0010, 0.0015, 0.0020, 0.0025]
sweep2    = []
for adx_t in adx_vals:
    trend_sw = df["ADX"] > adx_t
    for atrf in atrf_vals:
        ss_sw = (~is_panic & trend_sw & short_pb & ema_bear & slope_down & rsi_dn &
                 vol_ok & (df["ATR"]/df["Close"] >= atrf) &
                 (df["RSI"]>=RSI_LO_S) & (df["RSI"]<=RSI_HI_S))
        t, eq, _ = run_sim(df, FALSE, ss_sw, best_sl, best_tp, 2.5, 1.5)
        ret, pf, wr, mdd = quick_stats(t, eq)
        if ret is None: continue
        sweep2.append({"adx":adx_t,"atrf":atrf,"trades":len(t),"wr":wr,"pf":pf,"ret":ret,"mdd":mdd})
        mk = " <-" if ret >= 0 else ""
        print(f"  {adx_t:>5} {atrf*100:>5.2f}% | {len(t):>6} {wr:>6.1f} {pf:>7.3f} {ret:>8.2f}% {mdd:>7.2f}%{mk}")

print()
if sweep2:
    best2 = max(sweep2, key=lambda x: x["ret"])
    print(f"  Best: ADX>{best2['adx']} ATRf={best2['atrf']*100:.2f}% -> Ret={best2['ret']:+.2f}% PF={best2['pf']:.3f} WR={best2['wr']:.1f}% Trades={best2['trades']}")

# ── PHASE 4: Trail parameter sweep at best config so far ──────────────────────
best_adx  = best2["adx"]  if sweep2 else 25
best_atrf = best2["atrf"] if sweep2 else 0.0020
best_trend = df["ADX"] > best_adx
best_ss    = (~is_panic & best_trend & short_pb & ema_bear & slope_down & rsi_dn &
              vol_ok & (df["ATR"]/df["Close"] >= best_atrf) &
              (df["RSI"]>=RSI_LO_S) & (df["RSI"]<=RSI_HI_S))

print(f"\n=== PHASE 4: Trail sweep (Shorts, ADX>{best_adx} ATRf={best_atrf*100:.2f}% TP={best_tp} SL={best_sl}) ===")
print(f"  {'TrAct':>6} {'TrDist':>7} | {'Trades':>6} {'WR%':>6} {'PF':>7} {'Ret%':>8} {'MaxDD':>7}")
print("  " + "-"*54)

trail_act_vals  = [1.0, 1.5, 2.0, 2.5]
trail_dist_vals = [0.6, 0.8, 1.0, 1.5]
sweep3 = []
for ta in trail_act_vals:
    for td in trail_dist_vals:
        t, eq, _ = run_sim(df, FALSE, best_ss, best_sl, best_tp, ta, td)
        ret, pf, wr, mdd = quick_stats(t, eq)
        if ret is None: continue
        sweep3.append({"ta":ta,"td":td,"trades":len(t),"wr":wr,"pf":pf,"ret":ret,"mdd":mdd})
        mk = " <-" if ret >= 0 else ""
        print(f"  {ta:>6.1f} {td:>7.1f} | {len(t):>6} {wr:>6.1f} {pf:>7.3f} {ret:>8.2f}% {mdd:>7.2f}%{mk}")

print()
if sweep3:
    best3 = max(sweep3, key=lambda x: x["ret"])
    print(f"  Best: TrAct={best3['ta']} TrDist={best3['td']} -> Ret={best3['ret']:+.2f}% PF={best3['pf']:.3f}")

# ── PHASE 5: Additional filter tests on best short-only config ────────────────
best_ta = best3["ta"] if sweep3 else 1.5
best_td = best3["td"] if sweep3 else 0.8

# RSI 2-bar confirmation
rsi_dn2     = rsi_dn & (df["RSI"].shift(1) < df["RSI"].shift(2))
# Slope over 5 bars instead of 3
slope_dn5   = df["EMA_FAST"] < df["EMA_FAST"].shift(5)
# DI bear filter
di_bear     = df["DI_MINUS"] > df["DI_PLUS"]
# Strong bearish close (close in lower 50% of bar range)
bar_range   = (df["High"] - df["Low"]).replace(0, np.nan)
close_pos   = (df["Close"] - df["Low"]) / bar_range
strong_close_s = close_pos <= 0.50
# Higher vol filter
vol_ok_15   = df["Volume"] >= df["VOL_MA"] * 1.5

def test_shorts(extra_mask, label):
    ss = best_ss & extra_mask
    t, eq, _ = run_sim(df, FALSE, ss, best_sl, best_tp, best_ta, best_td)
    ret, pf, wr, mdd = quick_stats(t, eq)
    if ret is None:
        print(f"  {label:<25} | no trades")
        return None
    mk = " <-" if ret > best_ret_base else ""
    print(f"  {label:<25} | {len(t):>4}  WR={wr:.1f}%  PF={pf:.3f}  Ret={ret:+.2f}%  MaxDD={mdd:.2f}%{mk}")
    return {"label":label,"ret":ret,"pf":pf,"wr":wr,"trades":len(t),"mdd":mdd}

t_base, eq_base, _ = run_sim(df, FALSE, best_ss, best_sl, best_tp, best_ta, best_td)
ret_base, pf_base, wr_base, mdd_base = quick_stats(t_base, eq_base)
best_ret_base = ret_base or -99

print(f"\n=== PHASE 5: Additional filter isolation (vs base Ret={ret_base:+.2f}%) ===")
print(f"  {'Filter':<25} | {'N':>4}  {'WR':>6}  {'PF':>7}  {'Ret':>8}  {'MaxDD':>7}")
print("  " + "-"*63)
t_base_row, eq_b, _ = run_sim(df, FALSE, best_ss, best_sl, best_tp, best_ta, best_td)
rb, pb, wb, mb = quick_stats(t_base_row, eq_b)
print(f"  {'base (no extra filter)':<25} | {len(t_base_row):>4}  WR={wb:.1f}%  PF={pb:.3f}  Ret={rb:+.2f}%  MaxDD={mb:.2f}%")

extras = []
for mask, name in [
    (rsi_dn2,       "+ RSI 2-bar consec"),
    (slope_dn5,     "+ EMA slope 5 bars"),
    (di_bear,       "+ DI- > DI+"),
    (strong_close_s,"+ strong bearish close"),
    (vol_ok_15,     "+ vol >= 1.5x MA"),
    (rsi_dn2 & di_bear, "+ RSI2 + DI bear"),
    (di_bear & strong_close_s, "+ DI + strong close"),
    (rsi_dn2 & strong_close_s, "+ RSI2 + strong close"),
    (rsi_dn2 & di_bear & strong_close_s, "+ RSI2 + DI + close"),
]:
    r = test_shorts(mask, name)
    if r: extras.append(r)

# ── FINAL CONFIRMED RUN ───────────────────────────────────────────────────────
# Pick best combo from extras or stick with base
all_results = [{"label":"base","ret":ret_base,"pf":pf_base,"wr":wr_base,
                "trades":len(t_base),"mdd":mdd_base}] + extras
winner = max(all_results, key=lambda x: x["ret"])

print(f"\n=== FINAL CONFIG ===")
print(f"  Winner: '{winner['label']}'")
print(f"  Shorts-only  |  ADX>{best_adx}  ATRf={best_atrf*100:.2f}%")
print(f"  TP={best_tp}  SL={best_sl}  TrailAct={best_ta}  TrailDist={best_td}")
print(f"  Ret={winner['ret']:+.2f}%  PF={winner['pf']:.3f}  WR={winner['wr']:.1f}%  "
      f"Trades={winner['trades']}  MaxDD={winner['mdd']:.2f}%")

# Run final sim with winning extra filter to get trades + equity curve
if winner["label"] == "base":
    final_ss = best_ss
elif "+ RSI 2-bar consec" in winner["label"]:
    final_ss = best_ss & rsi_dn2
elif "+ EMA slope 5 bars" in winner["label"]:
    final_ss = best_ss & slope_dn5
elif "+ DI- > DI+" in winner["label"] and "strong" not in winner["label"] and "RSI2" not in winner["label"]:
    final_ss = best_ss & di_bear
elif "+ strong bearish close" in winner["label"]:
    final_ss = best_ss & strong_close_s
elif "+ vol >= 1.5x MA" in winner["label"]:
    final_ss = best_ss & vol_ok_15
elif "RSI2 + DI + close" in winner["label"]:
    final_ss = best_ss & rsi_dn2 & di_bear & strong_close_s
elif "RSI2 + DI" in winner["label"]:
    final_ss = best_ss & rsi_dn2 & di_bear
elif "DI + strong" in winner["label"]:
    final_ss = best_ss & di_bear & strong_close_s
elif "RSI2 + strong" in winner["label"]:
    final_ss = best_ss & rsi_dn2 & strong_close_s
else:
    final_ss = best_ss

t_final, eq_final, eqc_final = run_sim(df, FALSE, final_ss, best_sl, best_tp, best_ta, best_td)
ret_f, pf_f, wr_f, mdd_f = quick_stats(t_final, eq_final)

print("\n" + "="*60)
print(f"  APM v3.4  |  {TICKER} {INTERVAL}  (SHORTS ONLY)")
print("="*60)
print(f"  Initial capital :  ${INITIAL_CAP:>10,.2f}")
print(f"  Final equity    :  ${eq_final:>10,.2f}")
print(f"  Net P&L         : ${eq_final-INITIAL_CAP:>+10,.2f}")
print(f"  Return          :  {ret_f:>10.2f} %")
print(f"  Max drawdown    :  {mdd_f:>10.2f} %")
print(f"  Profit factor   :  {pf_f:>10.3f}")
print("-"*60)
wins = t_final[t_final["dollar_pnl"]>0]
loss = t_final[t_final["dollar_pnl"]<=0]
print(f"  Total trades    : {len(t_final):>6}")
print(f"  TP exits        : {(t_final['result']=='TP').sum():>6}")
print(f"  SL exits        : {(t_final['result']=='SL').sum():>6}")
print(f"  Win rate        :  {wr_f:>10.1f} %")
print(f"  Avg win         :  ${wins['dollar_pnl'].mean():>+9.2f}")
print(f"  Avg loss        :  ${loss['dollar_pnl'].mean():>+9.2f}" if not loss.empty else "  Avg loss        :       n/a")
print("="*60)


# Save CSV
out_csv = f"apm_v3_trades_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
t_final.to_csv(out_csv, index=False)
print(f"\nTrades CSV -> {out_csv}")

# ─── Dashboard export ──────────────────────────────────────────────────────────
from pathlib import Path as _Path
from scripts.dashboard_csv_utils import standardize_dashboard_csv
_dash_out = _Path(__file__).resolve().parent.parent.parent.parent / "docs" / "data" / "btcusd" / "v3_trades.csv"
std_tdf = standardize_dashboard_csv(t_final)
std_tdf.to_csv(_dash_out, index=False)
print(f"Dashboard export  → {_dash_out}")

# Equity chart
eq_df = pd.DataFrame(eqc_final).set_index("time")
fig, axes = plt.subplots(2, 1, figsize=(14, 7), gridspec_kw={"height_ratios":[3,1]})
ax1, ax2  = axes
ax1.plot(eq_df.index, eq_df["equity"], color="#63b3ed", linewidth=1.5)
ax1.axhline(INITIAL_CAP, color="#718096", linewidth=0.8, linestyle="--", alpha=0.7)
ax1.fill_between(eq_df.index, eq_df["equity"], INITIAL_CAP,
                 where=eq_df["equity"]>=INITIAL_CAP, alpha=0.15, color="#48bb78")
ax1.fill_between(eq_df.index, eq_df["equity"], INITIAL_CAP,
                 where=eq_df["equity"]<INITIAL_CAP,  alpha=0.15, color="#fc8181")
for _, tr in t_final.iterrows():
    ax1.axvline(tr["exit_time"], alpha=0.2,
                color="#48bb78" if tr["dollar_pnl"]>0 else "#fc8181", linewidth=0.6)
eq_s = pd.Series([e["equity"] for e in eqc_final])
dd   = (eq_s - eq_s.cummax()) / eq_s.cummax() * 100
ax2.fill_between(eq_df.index, dd.values, 0, color="#fc8181", alpha=0.6)
ax2.set_ylabel("Drawdown %")
ax2.set_ylim(min(dd.min()*1.1, -0.5), 1)
ax1.set_title(
    f"APM v3.4 Shorts-Only  |  {TICKER} {INTERVAL}  |  "
    f"Ret={ret_f:+.2f}%  PF={pf_f:.3f}  WR={wr_f:.1f}%  "
    f"Trades={len(t_final)}  MaxDD={mdd_f:.2f}%",
    color="#48bb78" if ret_f>=0 else "#fc8181", fontsize=10)
ax1.set_ylabel("Equity ($)")
for ax in [ax1, ax2]:
    ax.set_facecolor("#0d0d1a"); ax.tick_params(colors="#718096")
    ax.yaxis.label.set_color("#718096")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    for sp in ax.spines.values(): sp.set_edgecolor("#2d3748")
fig.patch.set_facecolor("#0d0d1a")
fig.autofmt_xdate(); plt.tight_layout()
out_png = f"apm_v3_equity_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
plt.savefig(out_png, dpi=150, bbox_inches="tight"); plt.close()
print(f"Chart       -> {out_png}")

print(f"\n>>> BEST CONFIG FOR PINE SCRIPT UPDATE <<<")
print(f"  Direction  = SHORTS ONLY")
print(f"  ADX_THRESH = {best_adx}")
print(f"  ATR_FLOOR  = {best_atrf*100:.2f}%")
print(f"  SL_MULT    = {best_sl}")
print(f"  TP_MULT    = {best_tp}")
print(f"  TRAIL_ACT  = {best_ta}")
print(f"  TRAIL_DIST = {best_td}")
print(f"  Extra filter: {winner['label']}")
