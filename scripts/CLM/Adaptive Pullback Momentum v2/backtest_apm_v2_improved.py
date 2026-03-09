# ─────────────────────────────────────────────────────────────────────────────
# APM v2  —  Indicator improvement study  (30m BTC-USD)
#
# CHANGES UNDER TEST vs v2.0 Pine Script defaults
#   1. Full EMA stack : EMA21 > EMA50 > EMA200 (long) / EMA21 < EMA50 < EMA200 (short)
#      Original only required EMA21>EMA50 and close>EMA200 — loose structural filter
#   2. EMA slope      : EMA21 must be rising/falling over 3 bars
#      Eliminates pullbacks into a flattening/reversing EMA
#   3. RSI direction  : RSI must be rising for longs / falling for shorts
#      Momentum confirmation on the recovery candle
#   4. Volume surge   : raised 1.0× → 1.2×  (entry must show above-avg conviction)
#   5. Min body       : raised 0.15× → 0.20×  (rejects weak doji-like recoveries)
#   6. ATR floor      : ATR ≥ 0.15% of price — eliminates low-vol bars where
#      fixed commission % eats more than half the theoretical edge
#   7. SL × 2.0, TP × 2.5  (sweep-optimised from 15m work; wider SL →
#      smaller notional → less commission drag, higher WR)
#   8. Panic mult     : tightened 1.5× → 1.3×  (exit volatile regimes sooner)
#   9. Trail activate : 2.5×  / trail dist : 1.5×  (let winners breathe
#      before trailing, then trail wider so small spikes don't stop out)
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

# ─── Configuration ─────────────────────────────────────────────────────────────
TICKER   = "BTC-USD"
PERIOD   = "max"
INTERVAL = "30m"

EMA_FAST   = 21
EMA_MID    = 50
EMA_SLOW   = 200
ADX_LEN    = 14
RSI_LEN    = 14
ATR_LEN    = 14
VOL_LEN    = 20
ATR_BL_LEN = 60

INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
RISK_PCT        = 0.01       # 1% equity risk per trade (unchanged)

# ── Improved parameters ────────────────────────────────────────────────────────
PB_PCT      = 0.15   # pullback tolerance % (unchanged — well-tuned)
ADX_THRESH  = 25     # ADX threshold (unchanged)
VOL_MULT    = 1.2    # ↑ from 1.0× — require above-avg volume conviction
MIN_BODY    = 0.20   # ↑ from 0.15× — filter weak doji-like candles
ATR_FLOOR   = 0.0015 # ↑ NEW — ATR ≥ 0.15% of price (kills high-commission entries)
SL_MULT     = 2.0    # ↑ from 1.5× — wider stop → smaller qty → less commission
TP_MULT     = 2.5    # ↑ from 2.0× — matches SL ratio for good R:R
TRAIL_ACT   = 2.5    # ↑ from 1.5× — let price travel before trailing kicks in
TRAIL_DIST  = 1.5    # ↑ from 0.8× — trail with room so micro-spikes don't exit
PANIC_MULT  = 1.3    # ↓ from 1.5× — exit volatile regimes more aggresively

RSI_LO_L = 42;  RSI_HI_L = 68
RSI_LO_S = 32;  RSI_HI_S = 58

TRADE_LONGS  = True
TRADE_SHORTS = True

# ─── Download ──────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                 auto_adjust=True, progress=False)
df.columns = df.columns.get_level_values(0)
df.index   = pd.to_datetime(df.index, utc=True)
df.sort_index(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}\n")

# ─── Indicators ────────────────────────────────────────────────────────────────
def ema(s, n):     return s.ewm(span=n, adjust=False).mean()
def sma(s, n):     return s.rolling(n).mean()
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

df["EMA_FAST"] = ema(df["Close"], EMA_FAST)
df["EMA_MID"]  = ema(df["Close"], EMA_MID)
df["EMA_SLOW"] = ema(df["Close"], EMA_SLOW)
df["RSI"]      = rsi_calc(df["Close"], RSI_LEN)
df["ATR"]      = atr_calc(df, ATR_LEN)
df["ATR_BL"]   = sma(df["ATR"], ATR_BL_LEN)
df["VOL_MA"]   = sma(df["Volume"], VOL_LEN)
df["DI_PLUS"], df["DI_MINUS"], df["ADX"] = adx_calc(df, ADX_LEN)
df.dropna(inplace=True)

# ─── Signal construction ───────────────────────────────────────────────────────
pb_tol_up  = df["EMA_FAST"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - PB_PCT / 100.0)
body_size  = (df["Close"] - df["Open"]).abs() / df["ATR"]

long_pb  = (df["Low"].shift(1)  <= pb_tol_up) & \
           (df["Close"] > df["EMA_FAST"]) & \
           (df["Close"] > df["Open"]) & \
           (body_size >= MIN_BODY)

short_pb = (df["High"].shift(1) >= pb_tol_dn) & \
           (df["Close"] < df["EMA_FAST"]) & \
           (df["Close"] < df["Open"]) & \
           (body_size >= MIN_BODY)

# ── NEW #1: Full EMA stack ──────────────────────────────────────────────────────
# Original: close>EMA200 and EMA21>EMA50 (allows EMA50<EMA200 if close above both)
# New:      EMA21 > EMA50 > EMA200 (all MAs in order — strongest structure)
ema_bull_full = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_bear_full = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])

# ── NEW #2: EMA slope filter ────────────────────────────────────────────────────
# EMA21 must be trending in the same direction as the intended trade over 3 bars
ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)

# ── NEW #3: RSI momentum direction ─────────────────────────────────────────────
# RSI must be rising on the recovery bar (longs) / falling (shorts)
rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)

# ── Unchanged filters ──────────────────────────────────────────────────────────
is_trending  = df["ADX"] > ADX_THRESH
is_panic     = df["ATR"] > df["ATR_BL"] * PANIC_MULT
vol_ok       = df["Volume"] >= df["VOL_MA"] * VOL_MULT
rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

# ── NEW #6: ATR floor ───────────────────────────────────────────────────────────
atr_pct_ok = df["ATR"] / df["Close"] >= ATR_FLOOR

# ─── Full entry conditions ──────────────────────────────────────────────────────
long_signal = (
    TRADE_LONGS &
    long_pb         &
    ema_bull_full   &   # full stack (stricter than original)
    ema_slope_up    &   # NEW
    rsi_rising      &   # NEW
    rsi_long_ok     &
    vol_ok          &
    is_trending     &
    ~is_panic       &
    atr_pct_ok          # NEW
)

short_signal = (
    TRADE_SHORTS &
    short_pb        &
    ema_bear_full   &   # full stack (stricter than original)
    ema_slope_down  &   # NEW
    rsi_falling     &   # NEW
    rsi_short_ok    &
    vol_ok          &
    is_trending     &
    ~is_panic       &
    atr_pct_ok          # NEW
)

# ─── Signal diagnostics ─────────────────────────────────────────────────────────
components_long = [
    ("long_pb",        long_pb),
    ("ema_bull_full",  ema_bull_full),
    ("ema_slope_up",   ema_slope_up),
    ("rsi_rising",     rsi_rising),
    ("rsi_long_ok",    rsi_long_ok),
    ("vol_ok",         vol_ok),
    ("is_trending",    is_trending),
    ("~is_panic",      ~is_panic),
    ("atr_pct_ok",     atr_pct_ok),
]
components_short = [
    ("short_pb",       short_pb),
    ("ema_bear_full",  ema_bear_full),
    ("ema_slope_down", ema_slope_down),
    ("rsi_falling",    rsi_falling),
    ("rsi_short_ok",   rsi_short_ok),
    ("vol_ok",         vol_ok),
    ("is_trending",    is_trending),
    ("~is_panic",      ~is_panic),
    ("atr_pct_ok",     atr_pct_ok),
]
print("--- Signal filter pass-through (long) ---")
cumulative = pd.Series([True]*len(df), index=df.index)
for name, mask in components_long:
    cumulative = cumulative & mask
    print(f"  {name:<18} → {cumulative.sum():>4} rows pass")
print("--- Signal filter pass-through (short) ---")
cumulative = pd.Series([True]*len(df), index=df.index)
for name, mask in components_short:
    cumulative = cumulative & mask
    print(f"  {name:<18} → {cumulative.sum():>4} rows pass")
print()
print(f"Improved signals — Long: {long_signal.sum()}  Short: {short_signal.sum()}")

# ─── Simulation helper ──────────────────────────────────────────────────────────
def run_sim(df, l_sig, s_sig, sl_m, tp_m, trail_a, trail_d, risk_pct,
            atr_floor=0.0, initial=10_000.0):
    eq  = initial
    pos = None
    trs = []
    eqc = []
    for ts, row in df.iterrows():
        close = float(row["Close"]); high = float(row["High"])
        low   = float(row["Low"]);   atr  = float(row["ATR"])
        htp = hsl = False
        xp  = pnl = 0.0
        d   = None
        if pos is not None:
            d = pos["d"]
            if d == "long":
                if high > pos["best"]: pos["best"] = high
                if pos["best"] >= pos["tap"]:
                    pos["sl"] = max(pos["sl"], pos["best"] - pos["tdf"])
                htp = high >= pos["tp"]
                hsl = low  <= pos["sl"]
            else:
                if low < pos["best"]: pos["best"] = low
                if pos["best"] <= pos["tap"]:
                    pos["sl"] = min(pos["sl"], pos["best"] + pos["tdf"])
                htp = low  <= pos["tp"]
                hsl = high >= pos["sl"]
            if htp or hsl:
                xp  = pos["tp"] if htp else pos["sl"]
                pnl = ((xp-pos["e"])/pos["e"] if d=="long"
                       else (pos["e"]-xp)/pos["e"])
        if htp or hsl:
            dp = pnl * pos["n"] - pos["n"] * COMMISSION_PCT * 2
            eq += dp
            trs.append({"entry_time": pos["et"], "exit_time": ts,
                        "direction": d, "entry": pos["e"], "exit": xp,
                        "result": "TP" if htp else "SL",
                        "pnl_pct": round(pnl*100,3),
                        "dollar_pnl": round(dp,2), "equity": round(eq,2)})
            pos = None
        if pos is None:
            sig = ("long"  if bool(l_sig[ts]) else
                   "short" if bool(s_sig[ts]) else None)
            if sig:
                if atr_floor > 0 and atr/close < atr_floor:
                    pass
                else:
                    sd  = atr * sl_m
                    n   = min(eq * risk_pct / sd * close, eq * 5.0)
                    sl  = close - sd if sig=="long" else close + sd
                    tp  = close + atr*tp_m if sig=="long" else close - atr*tp_m
                    tap = (close + atr*trail_a if sig=="long"
                           else close - atr*trail_a)
                    pos = {"d": sig, "e": close, "et": ts,
                           "sl": sl, "tp": tp, "best": close, "n": n,
                           "tap": tap, "tdf": atr*trail_d}
        eqc.append({"time": ts, "equity": eq})
    return pd.DataFrame(trs), eq, eqc

# ─── Main run ───────────────────────────────────────────────────────────────────
print("\n--- Running improved config ---")
tdf, final_eq, eqcurve = run_sim(df, long_signal, short_signal,
                                  SL_MULT, TP_MULT, TRAIL_ACT, TRAIL_DIST,
                                  RISK_PCT, ATR_FLOOR)

def print_stats(tdf, final_eq, label=""):
    if tdf.empty:
        print("No trades."); return
    wins  = tdf[tdf["dollar_pnl"] >  0]
    losss = tdf[tdf["dollar_pnl"] <= 0]
    wp    = len(wins)/len(tdf)*100
    ret   = (final_eq/INITIAL_CAPITAL-1)*100
    pf    = (wins["dollar_pnl"].sum()/abs(losss["dollar_pnl"].sum())
             if not losss.empty and losss["dollar_pnl"].sum()!=0 else float("inf"))
    rr    = (wins["dollar_pnl"].mean()/abs(losss["dollar_pnl"].mean())
             if not losss.empty else float("inf"))
    eq_s  = tdf["equity"]
    mdd   = 0.0
    pk    = INITIAL_CAPITAL
    for eq_v in eq_s:
        if eq_v > pk: pk = eq_v
        dd_v = (eq_v-pk)/pk*100
        if dd_v < mdd: mdd = dd_v
    print()
    print("=" * 60)
    print(f"  {label or 'APM v2 Improved'}  —  {TICKER} {INTERVAL}")
    print("=" * 60)
    print(f"  Initial capital   :  $ {INITIAL_CAPITAL:>10,.2f}")
    print(f"  Final equity      :  $ {final_eq:>10,.2f}")
    print(f"  Net P&L           : $ {final_eq-INITIAL_CAPITAL:>+10,.2f}")
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
    print(f"  Avg win           :  $ {wins['dollar_pnl'].mean():>+9.2f}")
    print(f"  Avg loss          :  $ {losss['dollar_pnl'].mean():>+9.2f}")
    print(f"  Avg R:R           :  {rr:>10.2f}")
    print(f"  Best trade        :  $ {tdf['dollar_pnl'].max():>+9.2f}")
    print(f"  Worst trade       :  $ {tdf['dollar_pnl'].min():>+9.2f}")
    print("=" * 60)
    for direction in ["long", "short"]:
        sub = tdf[tdf["direction"]==direction]
        if sub.empty: continue
        sw = sub[sub["dollar_pnl"]>0]; sl = sub[sub["dollar_pnl"]<=0]
        sub_wr = len(sw)/len(sub)*100
        sub_pf = (sw["dollar_pnl"].sum()/abs(sl["dollar_pnl"].sum())
                  if not sl.empty and sl["dollar_pnl"].sum()!=0 else float("inf"))
        print(f"  {direction.upper():<6} trades={len(sub):>3}  "
              f"WR={sub_wr:.0f}%  PF={sub_pf:.3f}  net=${sub['dollar_pnl'].sum():+.2f}")
    return ret, pf, wp, mdd

ret_i, pf_i, wr_i, mdd_i = print_stats(tdf, final_eq, "APM v2 Improved")

# ─── Comparison: original defaults ────────────────────────────────────────────
print("\n--- Rebuilding original signals for comparison ---")
pb_tol_up_o  = df["EMA_FAST"].shift(1) * (1.0 + 0.15 / 100.0)
pb_tol_dn_o  = df["EMA_FAST"].shift(1) * (1.0 - 0.15 / 100.0)
body_o       = (df["Close"] - df["Open"]).abs() / df["ATR"]
long_pb_o    = (df["Low"].shift(1) <= pb_tol_up_o) & (df["Close"] > df["EMA_FAST"]) & \
               (df["Close"] > df["Open"]) & (body_o >= 0.15)
short_pb_o   = (df["High"].shift(1) >= pb_tol_dn_o) & (df["Close"] < df["EMA_FAST"]) & \
               (df["Close"] < df["Open"]) & (body_o >= 0.15)
ema_bull_o   = (df["Close"] > df["EMA_SLOW"]) & (df["EMA_FAST"] > df["EMA_MID"])
ema_bear_o   = (df["Close"] < df["EMA_SLOW"]) & (df["EMA_FAST"] < df["EMA_MID"])
is_trend_o   = df["ADX"] > 25
is_panic_o   = df["ATR"] > df["ATR_BL"] * 1.5
vol_ok_o     = df["Volume"] >= df["VOL_MA"] * 1.0
rsi_l_o      = (df["RSI"] >= 42) & (df["RSI"] <= 68)
rsi_s_o      = (df["RSI"] >= 32) & (df["RSI"] <= 58)

long_sig_o   = long_pb_o  & ema_bull_o & rsi_l_o & vol_ok_o & is_trend_o & ~is_panic_o
short_sig_o  = short_pb_o & ema_bear_o & rsi_s_o & vol_ok_o & is_trend_o & ~is_panic_o

tdf_o, feq_o, _ = run_sim(df, long_sig_o, short_sig_o, 1.5, 2.0, 1.5, 0.8, 0.01, 0.0)
print_stats(tdf_o, feq_o, "APM v2.0 Original (baseline)")

# ─── Parameter sweep: TP × SL × ATR-floor (both long+short) ────────────────────
print("\n=== Sweep: TP × SL × ATR floor (improved signals, both directions) ===")
print(f"{'TP':>5} {'SL':>5} {'ATRf%':>6} | {'Trades':>6} {'WR%':>6} {'PF':>7} {'Ret%':>8}")
print("-" * 60)

tp_vals    = [2.0, 2.5, 3.0]
sl_vals    = [1.5, 2.0, 2.5]
atr_floors = [0.0, 0.10, 0.15, 0.20]
sweep_rows = []

for tp_m in tp_vals:
    for sl_m in sl_vals:
        for af in atr_floors:
            t, eq_sw, _ = run_sim(df, long_signal, short_signal,
                                   sl_m, tp_m, TRAIL_ACT, TRAIL_DIST, RISK_PCT, af/100)
            if t.empty: continue
            w    = t[t["dollar_pnl"]>0]; l = t[t["dollar_pnl"]<=0]
            wr_s = len(w)/len(t)*100
            ret_s= (eq_sw/INITIAL_CAPITAL-1)*100
            pf_s = (w["dollar_pnl"].sum()/abs(l["dollar_pnl"].sum())
                    if not l.empty and l["dollar_pnl"].sum()!=0 else float("inf"))
            sweep_rows.append({"TP":tp_m,"SL":sl_m,"ATRf":af,
                               "Trades":len(t),"WR":wr_s,"PF":pf_s,"Ret":ret_s})
            marker = " ←" if ret_s >= 0 else ""
            print(f"{tp_m:>5.1f} {sl_m:>5.1f} {af:>6.2f} | "
                  f"{len(t):>6} {wr_s:>6.1f} {pf_s:>7.3f} {ret_s:>8.2f}%{marker}")

if sweep_rows:
    best = max(sweep_rows, key=lambda x: x["PF"])
    bestR= max(sweep_rows, key=lambda x: x["Ret"])
    print(f"\nBest PF  : TP×{best['TP']} SL×{best['SL']} ATRf={best['ATRf']:.2f}% → "
          f"PF={best['PF']:.3f}  Ret={best['Ret']:+.2f}%  WR={best['WR']:.1f}%  Trades={best['Trades']}")
    print(f"Best Ret : TP×{bestR['TP']} SL×{bestR['SL']} ATRf={bestR['ATRf']:.2f}% → "
          f"PF={bestR['PF']:.3f}  Ret={bestR['Ret']:+.2f}%  WR={bestR['WR']:.1f}%  Trades={bestR['Trades']}")

# ─── Final run with best config ─────────────────────────────────────────────────
if sweep_rows:
    b = max(sweep_rows, key=lambda x: (x["Ret"], x["PF"]))
    print(f"\n--- Final confirmed run: TP×{b['TP']} SL×{b['SL']} ATRf={b['ATRf']:.2f}% ---")
    tdf_f, feq_f, eqcurve_f = run_sim(df, long_signal, short_signal,
                                        b["SL"], b["TP"], TRAIL_ACT, TRAIL_DIST,
                                        RISK_PCT, b["ATRf"]/100)
    ret_f, pf_f, wr_f, mdd_f = print_stats(tdf_f, feq_f,
        f"APM v2 Final  (TP×{b['TP']} SL×{b['SL']} ATRf={b['ATRf']:.2f}%)")

    # save CSV + chart for final config
    out_csv = f"apm_v2_improved_trades_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
    tdf_f.to_csv(out_csv, index=False)
    print(f"Trades CSV → {out_csv}")

    eq_df = pd.DataFrame(eqcurve_f).set_index("time")
    fig, axes = plt.subplots(2, 1, figsize=(14, 8),
                              gridspec_kw={"height_ratios": [3, 1]})
    ax1, ax2 = axes
    ax1.plot(eq_df.index, eq_df["equity"], color="#63b3ed", linewidth=1.5)
    ax1.axhline(INITIAL_CAPITAL, color="#718096", linewidth=0.8, linestyle="--", alpha=0.7)
    ax1.fill_between(eq_df.index, eq_df["equity"], INITIAL_CAPITAL,
                     where=eq_df["equity"] >= INITIAL_CAPITAL, alpha=0.15, color="#48bb78")
    ax1.fill_between(eq_df.index, eq_df["equity"], INITIAL_CAPITAL,
                     where=eq_df["equity"] <  INITIAL_CAPITAL, alpha=0.15, color="#fc8181")
    for _, t in tdf_f.iterrows():
        ax1.axvline(t["exit_time"], alpha=0.2,
                    color="#48bb78" if t["dollar_pnl"]>0 else "#fc8181", linewidth=0.6)

    eq_s  = pd.Series([e["equity"] for e in eqcurve_f])
    dd    = (eq_s - eq_s.cummax()) / eq_s.cummax() * 100
    ax2.fill_between(eq_df.index, dd.values, 0, color="#fc8181", alpha=0.6)
    ax2.set_ylabel("Drawdown %")
    ax2.set_ylim(min(dd.min()*1.1, -0.5), 1)

    color_ret = "#48bb78" if ret_f >= 0 else "#fc8181"
    ax1.set_title(
        f"APM v2 Improved  |  {TICKER} {INTERVAL}  |  "
        f"Return: {ret_f:+.2f}%  PF: {pf_f:.3f}  WR: {wr_f:.1f}%  "
        f"Trades: {len(tdf_f)}  MaxDD: {mdd_f:.2f}%",
        color=color_ret, fontsize=11)
    ax1.set_ylabel("Equity ($)")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate()
    fig.patch.set_facecolor("#0d0d1a")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#0d0d1a"); ax.tick_params(colors="#718096")
        ax.yaxis.label.set_color("#718096")
        for spine in ax.spines.values(): spine.set_edgecolor("#2d3748")
    ax1.title.set_color(color_ret)
    plt.tight_layout()
    out_png = f"apm_v2_improved_equity_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Chart → {out_png}")

    # store best params for Pine update
    print(f"\n>>> BEST CONFIG FOR PINE SCRIPT <<<")
    print(f"  SL_MULT   = {b['SL']}")
    print(f"  TP_MULT   = {b['TP']}")
    print(f"  ATR_FLOOR = {b['ATRf']:.2f}%")
    print(f"  VOL_MULT  = {VOL_MULT}")
    print(f"  MIN_BODY  = {MIN_BODY}")
    print(f"  TRAIL_ACT = {TRAIL_ACT}")
    print(f"  TRAIL_DIST= {TRAIL_DIST}")
    print(f"  PANIC_MULT= {PANIC_MULT}")
