# ─────────────────────────────────────────────────────────────────────────────
# APM v1.0 — CLM 5m  ·  12-Month 4-Stage Parameter Sweep
# Uses Alpaca for data (no 60-day yfinance cap — full 12 months of 5m bars)
#
# Stage 1: Sweep exit params (TP×, SL×, max_bars)
# Stage 2: Sweep signal filters (ADX, PB%, ATR floor, vol mult)
# Stage 3: Sweep trail params (trail_act, trail_dist)
# Stage 4: Sweep macro-bias filter (EMA_SLOW period + require bearish macro)
#          This is the key addition — avoids shorting in sustained up-regimes
#          (May, Sep–Dec 2025 were uptrend periods → shorts bled equity)
#
# Sort key: calmar (return/maxDD) to penalise deep drawdowns, min_trades=8
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys, itertools
for pkg in ["alpaca-py", "pandas", "numpy", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import pandas as pd
import numpy as np
import pytz, warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

_ET = pytz.timezone("America/New_York")

# ─── Alpaca credentials ────────────────────────────────────────────────────────
ALPACA_KEY    = "PKNIYXYVLHKHF43IIEUQIA42DJ"
ALPACA_SECRET = "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u"

TICKER          = "CLM"
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
RISK_PCT        = 0.01
MIN_TRADES      = 8    # raised to 8 for 12-month window (vs 4 for YTD)

# ── Fixed indicator periods ────────────────────────────────────────────────────
D_EMA_FAST = 21; D_EMA_MID = 50; D_EMA_SLOW = 200
D_ADX      = 14; D_RSI     = 14; D_ATR      = 14; D_VOL_N = 20
D_ATR_BL   = 60

# ── Fixed strategy params (never swept) ───────────────────────────────────────
D_ADX_SLOPE  = 0;   D_DI_SPREAD = 0.0;  D_EMA_SLOPE = 3
D_MOMENTUM   = 5;   D_MIN_BODY  = 0.15; D_PANIC     = 1.5
D_RSI_LO_S   = 30;  D_RSI_HI_S  = 58
D_SESSION_S  = 9;   D_SESSION_E = 14

# ── Starting-point defaults for sweep bounds ──────────────────────────────────
D_SL         = 3.0;  D_TP       = 4.0
D_TRAIL_ACT  = 3.5;  D_TRAIL_DIST = 0.2
D_MAX_BARS   = 0
D_ADX_THRESH = 12;   D_PB_PCT   = 0.25
D_VOL_MULT   = 0.3;  D_ATR_FLOOR = 0.0

CONSEC_LIMIT = 2; CONSEC_COOL = 1

# ─── Download 12m of 5m bars via Alpaca ───────────────────────────────────────
print(f"Downloading {TICKER} 5m via Alpaca (12 months) ...")
client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
TF5 = TimeFrame(5, TimeFrameUnit.Minute)
req = StockBarsRequest(
    symbol_or_symbols=TICKER,
    timeframe=TF5,
    start=datetime(2025, 3, 12, tzinfo=timezone.utc),
    end=datetime(2026, 3, 12, tzinfo=timezone.utc),
    feed=DataFeed.IEX,
)
bars = client.get_stock_bars(req)
raw = bars.df.reset_index(level=0, drop=True)
raw = raw.rename(columns={"open":"Open","high":"High","low":"Low",
                           "close":"Close","volume":"Volume"})
raw = raw[["Open","High","Low","Close","Volume"]].copy()
raw = raw[raw["Volume"] > 0].dropna()
raw.index = pd.to_datetime(raw.index, utc=True).tz_convert(_ET)
print(f"5m bars: {len(raw)}  |  {raw.index[0]} → {raw.index[-1]}")


# ─── Indicator + signal factory ───────────────────────────────────────────────
def build_indicators(df, adx_thresh=D_ADX_THRESH, pb_pct=D_PB_PCT,
                     vol_mult=D_VOL_MULT, atr_floor=D_ATR_FLOOR,
                     macro_ema=0):
    """
    macro_ema > 0 : add an extra bearish-macro gate — only take shorts when
                    Close < EMA(macro_ema). Filters out shorting in uptrends.
    """
    d = df.copy()
    d["EF"] = d["Close"].ewm(span=D_EMA_FAST, adjust=False).mean()
    d["EM"] = d["Close"].ewm(span=D_EMA_MID,  adjust=False).mean()
    d["ES"] = d["Close"].ewm(span=D_EMA_SLOW, adjust=False).mean()

    if macro_ema > 0:
        d["MACRO"] = d["Close"].ewm(span=macro_ema, adjust=False).mean()
    # (no MACRO column when off — avoids polluting dropna)

    delta = d["Close"].diff()
    g = delta.clip(lower=0).ewm(alpha=1/D_RSI, adjust=False).mean()
    l = (-delta).clip(lower=0).ewm(alpha=1/D_RSI, adjust=False).mean()
    d["RSI"] = 100 - (100 / (1 + g / l.replace(0, 1e-10)))

    hl  = d["High"] - d["Low"]
    hpc = (d["High"] - d["Close"].shift(1)).abs()
    lpc = (d["Low"]  - d["Close"].shift(1)).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    d["ATR"]    = tr.ewm(alpha=1/D_ATR, adjust=False).mean()
    d["ATR_BL"] = d["ATR"].rolling(D_ATR_BL).mean()
    d["VOL_MA"] = d["Volume"].rolling(D_VOL_N).mean()

    up = d["High"] - d["High"].shift(1)
    dn = d["Low"].shift(1) - d["Low"]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    sp = pd.Series(pdm, index=d.index).ewm(alpha=1/D_ADX, adjust=False).mean()
    sm = pd.Series(ndm, index=d.index).ewm(alpha=1/D_ADX, adjust=False).mean()
    d["DI+"] = 100 * sp / d["ATR"].replace(0, 1e-10)
    d["DI-"] = 100 * sm / d["ATR"].replace(0, 1e-10)
    dx = 100 * (d["DI+"] - d["DI-"]).abs() / (d["DI+"] + d["DI-"]).replace(0, 1e-10)
    d["ADX"] = dx.ewm(alpha=1/D_ADX, adjust=False).mean()
    d.dropna(inplace=True)
    d["ET_HOUR"] = d.index.hour

    # ── Signal components ──────────────────────────────────────────────────────
    tol      = pb_pct / 100.0
    pb_dn    = d["EF"].shift(1) * (1.0 - tol)
    short_pb = ((d["High"].shift(1) >= pb_dn) &
                (d["Close"] < d["EF"]) & (d["Close"] < d["Open"]))
    ema_bear   = (d["EF"] < d["EM"]) & (d["EM"] < d["ES"])
    ema_sl_dn  = d["EF"] < d["EF"].shift(D_EMA_SLOPE)
    rsi_fall   = d["RSI"] < d["RSI"].shift(1)
    rsi_ok_s   = (d["RSI"] >= D_RSI_LO_S) & (d["RSI"] <= D_RSI_HI_S)
    vol_ok     = d["Volume"] >= d["VOL_MA"] * vol_mult
    body_ok    = (d["Close"] - d["Open"]).abs() / d["ATR"].replace(0, 1e-10) >= D_MIN_BODY
    is_trend   = d["ADX"] > adx_thresh
    not_panic  = d["ATR"] <= d["ATR_BL"] * D_PANIC
    atr_fl_ok  = (d["ATR"] / d["Close"] >= atr_floor) if atr_floor > 0 else pd.Series(True, index=d.index)
    mom_ok     = d["Close"] < d["Close"].shift(D_MOMENTUM)
    di_ok      = (d["DI-"] - d["DI+"]) >= D_DI_SPREAD
    adx_up     = pd.Series(True, index=d.index)
    session    = (d["ET_HOUR"] >= D_SESSION_S) & (d["ET_HOUR"] < D_SESSION_E)

    # Macro bearish gate (off when macro_ema=0)
    if macro_ema > 0:
        macro_bear = d["Close"] < d["MACRO"]
    else:
        macro_bear = pd.Series(True, index=d.index)

    short_sig = (short_pb & ema_bear & ema_sl_dn & rsi_fall & rsi_ok_s &
                 vol_ok & body_ok & is_trend & not_panic & atr_fl_ok &
                 adx_up & di_ok & mom_ok & session & macro_bear)
    long_sig  = pd.Series(False, index=d.index)
    return d, long_sig, short_sig


# ─── Bar-by-bar simulator ─────────────────────────────────────────────────────
def simulate(df_sim, ls, ss, sl_m, tp_m, trail_act, trail_dist, max_bars):
    H  = df_sim["High"].values;   L  = df_sim["Low"].values
    C  = df_sim["Close"].values;  AT = df_sim["ATR"].values
    LS = ls.values;               SS = ss.values

    equity  = INITIAL_CAPITAL
    pos     = None
    pnls    = []
    results = []
    consec  = 0; cool = 0

    for i in range(len(df_sim)):
        atr_i = AT[i]
        if np.isnan(atr_i) or atr_i == 0:
            continue
        sd = atr_i * sl_m

        if pos is not None:
            pos["bars"] += 1
            d = pos["dir"]
            if d == "short":
                if L[i] < pos["best"]: pos["best"] = L[i]
                if pos["best"] <= pos["entry"] - atr_i * trail_act:
                    new_sl = pos["best"] + atr_i * trail_dist
                    if new_sl < pos["sl"]: pos["sl"] = new_sl
                if max_bars > 0 and pos["bars"] >= max_bars:
                    xp  = C[i]
                    raw = (pos["entry"] - xp) / pos["entry"]
                    dp  = raw * pos["notl"] - pos["notl"] * COMMISSION_PCT * 2
                    equity += dp; pnls.append(dp); results.append("MB")
                    consec, cool = _cc(dp, consec, cool)
                    pos = None; continue
                hit_tp = L[i] <= pos["tp"]
                hit_sl = H[i] >= pos["sl"]
                if hit_tp or hit_sl:
                    xp  = pos["tp"] if hit_tp else pos["sl"]
                    raw = (pos["entry"] - xp) / pos["entry"]
                    dp  = raw * pos["notl"] - pos["notl"] * COMMISSION_PCT * 2
                    equity += dp; pnls.append(dp)
                    results.append("TP" if hit_tp else "SL")
                    consec, cool = _cc(dp, consec, cool)
                    pos = None
            else:
                if H[i] > pos["best"]: pos["best"] = H[i]
                if pos["best"] >= pos["entry"] + atr_i * trail_act:
                    new_sl = pos["best"] - atr_i * trail_dist
                    if new_sl > pos["sl"]: pos["sl"] = new_sl
                if max_bars > 0 and pos["bars"] >= max_bars:
                    xp  = C[i]
                    raw = (xp - pos["entry"]) / pos["entry"]
                    dp  = raw * pos["notl"] - pos["notl"] * COMMISSION_PCT * 2
                    equity += dp; pnls.append(dp); results.append("MB")
                    consec, cool = _cc(dp, consec, cool)
                    pos = None; continue
                hit_tp = H[i] >= pos["tp"]
                hit_sl = L[i] <= pos["sl"]
                if hit_tp or hit_sl:
                    xp  = pos["tp"] if hit_tp else pos["sl"]
                    raw = (xp - pos["entry"]) / pos["entry"]
                    dp  = raw * pos["notl"] - pos["notl"] * COMMISSION_PCT * 2
                    equity += dp; pnls.append(dp)
                    results.append("TP" if hit_tp else "SL")
                    consec, cool = _cc(dp, consec, cool)
                    pos = None

        if pos is None:
            if cool > 0:
                cool -= 1
            else:
                sig = "short" if SS[i] else ("long" if LS[i] else None)
                if sig:
                    notl = min(equity * RISK_PCT / sd * C[i], equity * 5.0)
                    if sig == "short":
                        pos = {"dir":"short","entry":C[i],"best":C[i],
                               "sl":C[i]+sd,"tp":C[i]-atr_i*tp_m,"notl":notl,"bars":0}
                    else:
                        pos = {"dir":"long","entry":C[i],"best":C[i],
                               "sl":C[i]-sd,"tp":C[i]+atr_i*tp_m,"notl":notl,"bars":0}

    if not pnls or len(pnls) < MIN_TRADES:
        return None
    arr  = np.array(pnls)
    wins = arr[arr > 0]; losses = arr[arr <= 0]
    n    = len(arr)
    gp   = wins.sum() if len(wins) else 0
    gl   = abs(losses.sum()) if len(losses) else 0
    pf   = gp / gl if gl > 0 else float("inf")
    net_pct = arr.sum() / INITIAL_CAPITAL * 100
    eq = INITIAL_CAPITAL; peak = INITIAL_CAPITAL; max_dd = 0.0
    for dp in pnls:
        eq += dp
        if eq > peak: peak = eq
        dd = (eq - peak) / peak * 100
        if dd < max_dd: max_dd = dd
    calmar = net_pct / abs(max_dd) if max_dd < 0 else (net_pct if net_pct > 0 else 0.0)
    tps = results.count("TP"); sls = results.count("SL"); mbs = results.count("MB")
    return {"trades":n, "wr":round(len(wins)/n*100,1), "pf":round(pf,3),
            "net_pct":round(net_pct,2), "max_dd":round(max_dd,2),
            "calmar":round(calmar,3), "tp":tps, "sl":sls, "mb":mbs}


def _cc(dp, consec, cool):
    if dp <= 0:
        consec += 1
        if consec >= CONSEC_LIMIT: cool = CONSEC_COOL; consec = 0
    else:
        consec = 0
    return consec, cool


def top_n(rows, n=15, key="calmar"):
    return sorted(rows, key=lambda r: r[key], reverse=True)[:n]

def print_table(rows, param_keys, title):
    print(f"\n{'═'*100}")
    print(f"  {title}")
    print(f"{'═'*100}")
    hdr   = " | ".join(f"{k:>12}" for k in param_keys)
    stats = "trades |    wr%  |    pf   | net_pct |  max_dd | calmar | tp/sl/mb"
    print(f"  {hdr}  ||  {stats}")
    print(f"  {'-'*98}")
    for r in rows:
        vals = " | ".join(f"{r[k]:>12}" for k in param_keys)
        print(f"  {vals}  ||"
              f"  {r['trades']:>4}  | {r['wr']:>6.1f}% | {r['pf']:>7.3f} |"
              f" {r['net_pct']:>+7.2f}% | {r['max_dd']:>6.2f}% | {r['calmar']:>6.3f} |"
              f" {r['tp']}/{r['sl']}/{r['mb']}")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — Exit parameter sweep (signals fixed at sweep-optimised defaults)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print("  STAGE 1 — Sweep TP×, SL×, max_bars  (no macro filter yet)")
print("═"*70)

# Build signals once with current-best params, no macro filter
df_base, ls_base, ss_base = build_indicators(raw,
    adx_thresh=D_ADX_THRESH, pb_pct=D_PB_PCT,
    vol_mult=D_VOL_MULT, atr_floor=D_ATR_FLOOR, macro_ema=0)
print(f"Total bars (indicator warmup stripped): {len(df_base)}")
print(f"Signals: {ss_base.sum()} short")

s1_tp      = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
s1_sl      = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
s1_maxbars = [0, 12, 24, 36, 48]

s1_rows = []
total_s1 = sum(1 for tp, sl, mb in itertools.product(s1_tp, s1_sl, s1_maxbars) if tp > sl)
print(f"Combos: {total_s1}")

for tp, sl, mb in itertools.product(s1_tp, s1_sl, s1_maxbars):
    if tp <= sl:
        continue
    r = simulate(df_base, ls_base, ss_base,
                 sl_m=sl, tp_m=tp, trail_act=D_TRAIL_ACT,
                 trail_dist=D_TRAIL_DIST, max_bars=mb)
    if r is None:
        continue
    r.update({"tp_m": tp, "sl_m": sl, "max_bars": mb})
    s1_rows.append(r)

s1_best = top_n(s1_rows, 15, key="calmar")
print_table(s1_best, ["tp_m","sl_m","max_bars"], "TOP 15 by Calmar — Stage 1 (exit params)")

b1 = s1_best[0]
BEST_TP = b1["tp_m"]; BEST_SL = b1["sl_m"]; BEST_MB = b1["max_bars"]
print(f"\n→ Stage-1 winner:  TP×{BEST_TP}  SL×{BEST_SL}  max_bars={BEST_MB}"
      f"  ({b1['trades']}T  WR={b1['wr']}%  PF={b1['pf']}  net={b1['net_pct']:+.2f}%  Calmar={b1['calmar']})")

pd.DataFrame(s1_rows).sort_values("calmar", ascending=False).to_csv("sweep12_s1_exit.csv", index=False)
print("Stage-1 results → sweep12_s1_exit.csv")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — Signal filter sweep (exits locked from S1)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print(f"  STAGE 2 — Sweep ADX, PB%, ATR floor, vol×  |  exits: TP×{BEST_TP} SL×{BEST_SL}")
print("═"*70)

s2_adx  = [8, 10, 12, 15, 18, 20, 25]
s2_pb   = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
s2_atrf = [0.0, 0.0005, 0.0010]
s2_vol  = [0.2, 0.3, 0.5, 0.7, 1.0]

total_s2 = len(s2_adx) * len(s2_pb) * len(s2_atrf) * len(s2_vol)
print(f"Combos: {total_s2}  (rebuilds signals each time)")

s2_rows = []
for adx, pb, atrf, vol in itertools.product(s2_adx, s2_pb, s2_atrf, s2_vol):
    df_f, ls_f, ss_f = build_indicators(raw,
        adx_thresh=adx, pb_pct=pb, vol_mult=vol, atr_floor=atrf, macro_ema=0)
    r = simulate(df_f, ls_f, ss_f,
                 sl_m=BEST_SL, tp_m=BEST_TP, trail_act=D_TRAIL_ACT,
                 trail_dist=D_TRAIL_DIST, max_bars=BEST_MB)
    if r is None:
        continue
    r.update({"adx": adx, "pb_pct": pb, "atr_floor": atrf, "vol_mult": vol})
    s2_rows.append(r)

s2_best = top_n(s2_rows, 15, key="calmar")
print_table(s2_best, ["adx","pb_pct","atr_floor","vol_mult"], "TOP 15 by Calmar — Stage 2 (signal filters)")

b2 = s2_best[0]
BEST_ADX = b2["adx"]; BEST_PB = b2["pb_pct"]
BEST_ATRF = b2["atr_floor"]; BEST_VOL = b2["vol_mult"]
print(f"\n→ Stage-2 winner:  ADX={BEST_ADX}  PB={BEST_PB}%  ATR_f={BEST_ATRF*100:.3f}%  vol×{BEST_VOL}"
      f"  ({b2['trades']}T  WR={b2['wr']}%  net={b2['net_pct']:+.2f}%  Calmar={b2['calmar']})")

pd.DataFrame(s2_rows).sort_values("calmar", ascending=False).to_csv("sweep12_s2_signal.csv", index=False)
print("Stage-2 results → sweep12_s2_signal.csv")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — Trail parameter sweep (S1+S2 locked)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print(f"  STAGE 3 — Sweep trail_act, trail_dist")
print(f"            Exits: TP×{BEST_TP} SL×{BEST_SL}  Signals: ADX={BEST_ADX} PB={BEST_PB}% vol×{BEST_VOL}")
print("═"*70)

df_s3, ls_s3, ss_s3 = build_indicators(raw,
    adx_thresh=BEST_ADX, pb_pct=BEST_PB, vol_mult=BEST_VOL,
    atr_floor=BEST_ATRF, macro_ema=0)
print(f"Signals for Stage-3: {ss_s3.sum()} short")

s3_ta = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 99.0]
s3_td = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]
total_s3 = len(s3_ta) * len(s3_td)
print(f"Combos: {total_s3}")

s3_rows = []
for ta, td in itertools.product(s3_ta, s3_td):
    r = simulate(df_s3, ls_s3, ss_s3,
                 sl_m=BEST_SL, tp_m=BEST_TP, trail_act=ta,
                 trail_dist=td, max_bars=BEST_MB)
    if r is None:
        continue
    r.update({"trail_act": ta, "trail_dist": td})
    s3_rows.append(r)

s3_best = top_n(s3_rows, 15, key="calmar")
print_table(s3_best, ["trail_act","trail_dist"], "TOP 15 by Calmar — Stage 3 (trail params)")

b3 = s3_best[0]
BEST_TA = b3["trail_act"]; BEST_TD = b3["trail_dist"]
print(f"\n→ Stage-3 winner:  trail_act={BEST_TA}  trail_dist={BEST_TD}"
      f"  ({b3['trades']}T  WR={b3['wr']}%  net={b3['net_pct']:+.2f}%  Calmar={b3['calmar']})")

pd.DataFrame(s3_rows).sort_values("calmar", ascending=False).to_csv("sweep12_s3_trail.csv", index=False)
print("Stage-3 results → sweep12_s3_trail.csv")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — Macro-bias filter sweep  (all S1-S3 locked)
# Key insight: May, Sep–Dec 2025 CLM was in an uptrend — shorts bled equity.
# Adding a long-period EMA gate (only short when close < macro_ema) avoids
# fighting the trend on the daily/weekly timeframe.
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print(f"  STAGE 4 — Sweep macro-bias EMA period (0 = off)")
print(f"            All other params locked from Stages 1-3")
print("═"*70)

# macro_ema=0 means OFF (no filter); test longer-period EMAs as regime gates
s4_macro = [0, 100, 150, 200, 300, 400, 500, 600, 800, 1000, 1500, 2000]
print(f"Combos: {len(s4_macro)}")

s4_rows = []
for macro in s4_macro:
    df_f, ls_f, ss_f = build_indicators(raw,
        adx_thresh=BEST_ADX, pb_pct=BEST_PB, vol_mult=BEST_VOL,
        atr_floor=BEST_ATRF, macro_ema=macro)
    r = simulate(df_f, ls_f, ss_f,
                 sl_m=BEST_SL, tp_m=BEST_TP, trail_act=BEST_TA,
                 trail_dist=BEST_TD, max_bars=BEST_MB)
    if r is None:
        s4_rows.append({"macro_ema": macro, "trades":0,"wr":0,"pf":0,
                        "net_pct":0,"max_dd":0,"calmar":0,"tp":0,"sl":0,"mb":0})
        continue
    r.update({"macro_ema": macro})
    s4_rows.append(r)

s4_best = sorted([r for r in s4_rows if r["trades"] >= MIN_TRADES],
                 key=lambda r: r["calmar"], reverse=True)[:15]
print_table(s4_best, ["macro_ema"], "TOP results by Calmar — Stage 4 (macro EMA gate)")

b4 = s4_best[0] if s4_best else {"macro_ema": 0}
BEST_MACRO = b4["macro_ema"]
print(f"\n→ Stage-4 winner:  macro_ema={BEST_MACRO}"
      f"  ({b4.get('trades',0)}T  WR={b4.get('wr',0)}%"
      f"  net={b4.get('net_pct',0):+.2f}%  Calmar={b4.get('calmar',0)})")

pd.DataFrame(s4_rows).sort_values("calmar", ascending=False).to_csv("sweep12_s4_macro.csv", index=False)
print("Stage-4 results → sweep12_s4_macro.csv")


# ══════════════════════════════════════════════════════════════════════════════
# FINAL VALIDATION — all stages combined
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print("  FINAL VALIDATION — all best params combined")
print("═"*70)

df_fin, ls_fin, ss_fin = build_indicators(raw,
    adx_thresh=BEST_ADX, pb_pct=BEST_PB, vol_mult=BEST_VOL,
    atr_floor=BEST_ATRF, macro_ema=BEST_MACRO)
r_fin = simulate(df_fin, ls_fin, ss_fin,
                 sl_m=BEST_SL, tp_m=BEST_TP, trail_act=BEST_TA,
                 trail_dist=BEST_TD, max_bars=BEST_MB)

print(f"""
  Parameters chosen:
    ADX={BEST_ADX}  PB={BEST_PB}%  vol×{BEST_VOL}  ATR_floor={BEST_ATRF*100:.3f}%
    SL×{BEST_SL}  TP×{BEST_TP}  trail_act={BEST_TA}  trail_dist={BEST_TD}  max_bars={BEST_MB}
    macro_ema={BEST_MACRO} {'(off)' if BEST_MACRO == 0 else f'(close < EMA{BEST_MACRO})'}
""")

if r_fin:
    print(f"  Trades  : {r_fin['trades']}   WR: {r_fin['wr']:.1f}%   PF: {r_fin['pf']:.3f}")
    print(f"  Net P&L : {r_fin['net_pct']:+.2f}%   Max DD: {r_fin['max_dd']:.2f}%   Calmar: {r_fin['calmar']:.3f}")
    print(f"  TP: {r_fin['tp']}   SL: {r_fin['sl']}   MB: {r_fin['mb']}")
    print(f"""
┌─────────────────────────────────────────────────────┐
│  Before  12T  WR=43.9%  PF=0.650  net=-21.31% ← baseline
│  After   {r_fin['trades']:>2}T  WR={r_fin['wr']:.1f}%  PF={r_fin['pf']:.3f}  net={r_fin['net_pct']:+.2f}%
└─────────────────────────────────────────────────────┘""")
else:
    print("  No trades fired with combined params.")
