# ─────────────────────────────────────────────────────────────────────────────
# APM v1.0 — CLM 5m  ·  3-Stage Parameter Sweep
#
# Stage 1: Sweep exit params (TP×, SL×, max_bars) — signals fixed at defaults
#          Isolates the pure exit model problem (0 TP exits at 6×ATR)
#
# Stage 2: Using Stage-1 best exits, sweep signal filters (ADX, PB%, ATR floor,
#          vol mult) to maximise trade count without degrading WR
#
# Stage 3: Using Stage-1+2 bests, sweep trail params (trail_act, trail_dist)
#
# Sort key: net_pct (maximise return) with min_trades guard (>=5)
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys, itertools
for pkg in ["yfinance", "pandas", "numpy", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])


import yfinance as yf
import pandas as pd
import numpy as np
import pytz, warnings
warnings.filterwarnings("ignore")
from indicators_signals import build_indicators_signals

_ET = pytz.timezone("America/New_York")

TICKER          = "CLM"
YTD_START       = pd.Timestamp("2026-01-01", tz="America/New_York")
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
RISK_PCT        = 0.01
MIN_TRADES      = 4    # minimum trades for a result to be included in ranking

# ── Fixed defaults (matches Pine v1.0 5m) ─────────────────────────────────────
D_EMA_FAST     = 21;   D_EMA_MID  = 50;  D_EMA_SLOW = 200
D_ADX          = 14;   D_RSI      = 14;  D_ATR      = 14;  D_VOL_N = 20
D_ATR_BL       = 60
D_ADX_THRESH   = 20
D_ADX_SLOPE    = 0     # off
D_DI_SPREAD    = 0.0   # off
D_EMA_SLOPE    = 3
D_MOMENTUM     = 5
D_PB_PCT       = 0.20
D_VOL_MULT     = 0.7
D_MIN_BODY     = 0.15
D_ATR_FLOOR    = 0.0015  # 0.15%
D_PANIC        = 1.5
D_RSI_LO_S     = 30;  D_RSI_HI_S = 58
D_RSI_LO_L     = 42;  D_RSI_HI_L = 68
D_SESSION_S    = 9;   D_SESSION_E = 14

D_SL           = 2.0
D_TP           = 6.0
D_TRAIL_ACT    = 3.5
D_TRAIL_DIST   = 0.3
D_MAX_BARS     = 30

CONSEC_LIMIT   = 2
CONSEC_COOL    = 1

# ─── Download ─────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} 5m ...")
raw = yf.download(TICKER, period="60d", interval="5m",
                  auto_adjust=True, progress=False)
if raw.empty:
    raise SystemExit(f"No data for {TICKER}.")
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)
raw = raw[["Open","High","Low","Close","Volume"]].copy()
raw = raw[raw["Volume"] > 0].dropna()
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw.index = raw.index.tz_convert(_ET)
print(f"5m bars: {len(raw)}  |  {raw.index[0]} → {raw.index[-1]}")


# ─── Indicator factory ─────────────────────────────────────────────────────────

# Use shared indicator/signal logic
def build_indicators(df, adx_thresh, pb_pct, vol_mult, atr_floor):
    d, long_sig, short_sig = build_indicators_signals(
        df,
        ema_fast=D_EMA_FAST, ema_mid=D_EMA_MID, ema_slow=D_EMA_SLOW,
        adx_len=D_ADX, rsi_len=D_RSI, atr_len=D_ATR, vol_len=D_VOL_N, atr_bl_len=D_ATR_BL,
        adx_thresh=adx_thresh, pb_pct=pb_pct, vol_mult=vol_mult, atr_floor=atr_floor, panic_mult=D_PANIC,
        ema_slope_bars=D_EMA_SLOPE, momentum_bars=D_MOMENTUM, min_body=D_MIN_BODY,
        di_spread_min=D_DI_SPREAD, adx_slope_bars=D_ADX_SLOPE,
        rsi_lo_s=D_RSI_LO_S, rsi_hi_s=D_RSI_HI_S, rsi_lo_l=D_RSI_LO_L, rsi_hi_l=D_RSI_HI_L,
        session_start=D_SESSION_S, session_end=D_SESSION_E,
        trade_longs=False, trade_shorts=True
    )
    return d, long_sig, short_sig


# ─── Bar-by-bar simulator (accepts precomputed signals) ───────────────────────
def simulate(df_ytd, ls_ytd, ss_ytd, sl_m, tp_m, trail_act, trail_dist, max_bars):
    H  = df_ytd["High"].values;   L  = df_ytd["Low"].values
    C  = df_ytd["Close"].values;  AT = df_ytd["ATR"].values
    LS = ls_ytd.values;           SS = ss_ytd.values

    equity   = INITIAL_CAPITAL
    pos      = None
    pnls     = []
    results  = []
    consec   = 0
    cool     = 0

    for i in range(len(df_ytd)):
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
                # max bars
                if max_bars > 0 and pos["bars"] >= max_bars:
                    xp = C[i]
                    raw = (pos["entry"] - xp) / pos["entry"]
                    dp  = raw * pos["notl"] - pos["notl"] * COMMISSION_PCT * 2
                    equity += dp; pnls.append(dp); results.append("MB")
                    consec, cool = _cc(dp, consec, cool)
                    pos = None; continue
                hit_tp = L[i] <= pos["tp"]
                hit_sl = H[i] >= pos["sl"]
                if hit_tp or hit_sl:
                    xp = pos["tp"] if hit_tp else pos["sl"]
                    raw = (pos["entry"] - xp) / pos["entry"]
                    dp  = raw * pos["notl"] - pos["notl"] * COMMISSION_PCT * 2
                    equity += dp; pnls.append(dp)
                    results.append("TP" if hit_tp else "SL")
                    consec, cool = _cc(dp, consec, cool)
                    pos = None
            else:  # long
                if H[i] > pos["best"]: pos["best"] = H[i]
                if pos["best"] >= pos["entry"] + atr_i * trail_act:
                    new_sl = pos["best"] - atr_i * trail_dist
                    if new_sl > pos["sl"]: pos["sl"] = new_sl
                if max_bars > 0 and pos["bars"] >= max_bars:
                    xp = C[i]
                    raw = (xp - pos["entry"]) / pos["entry"]
                    dp  = raw * pos["notl"] - pos["notl"] * COMMISSION_PCT * 2
                    equity += dp; pnls.append(dp); results.append("MB")
                    consec, cool = _cc(dp, consec, cool)
                    pos = None; continue
                hit_tp = H[i] >= pos["tp"]
                hit_sl = L[i] <= pos["sl"]
                if hit_tp or hit_sl:
                    xp = pos["tp"] if hit_tp else pos["sl"]
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
                        pos = {"dir": "short", "entry": C[i], "best": C[i],
                               "sl": C[i] + sd, "tp": C[i] - atr_i * tp_m,
                               "notl": notl, "bars": 0}
                    else:
                        pos = {"dir": "long", "entry": C[i], "best": C[i],
                               "sl": C[i] - sd, "tp": C[i] + atr_i * tp_m,
                               "notl": notl, "bars": 0}

    if not pnls:
        return None
    arr  = np.array(pnls)
    wins = arr[arr > 0]; losses = arr[arr <= 0]
    n = len(arr)
    if n < MIN_TRADES:
        return None
    gp = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0
    pf = gp / gl if gl > 0 else float("inf")
    net_pct = arr.sum() / INITIAL_CAPITAL * 100
    # drawdown
    eq = INITIAL_CAPITAL
    peak = INITIAL_CAPITAL
    max_dd = 0.0
    for dp in pnls:
        eq += dp
        if eq > peak: peak = eq
        dd = (eq - peak) / peak * 100
        if dd < max_dd: max_dd = dd
    calmar = net_pct / abs(max_dd) if max_dd < 0 else float("inf")
    tps = results.count("TP"); sls = results.count("SL"); mbs = results.count("MB")
    return {"trades": n, "wr": round(len(wins)/n*100,1), "pf": round(pf,3),
            "net_pct": round(net_pct,2), "max_dd": round(max_dd,2),
            "calmar": round(calmar,3), "tp": tps, "sl": sls, "mb": mbs}


def _cc(dp, consec, cool):
    if dp <= 0:
        consec += 1
        if consec >= CONSEC_LIMIT: cool = CONSEC_COOL; consec = 0
    else:
        consec = 0
    return consec, cool


def top_n(rows, n=10, key="net_pct"):
    return sorted(rows, key=lambda r: r[key], reverse=True)[:n]

def print_table(rows, param_keys, title):
    print(f"\n{'═'*90}")
    print(f"  {title}")
    print(f"{'═'*90}")
    hdr = " | ".join(f"{k:>10}" for k in param_keys)
    stats = "trades |    wr%  |    pf   | net_pct | max_dd  | calmar | tp/sl/mb"
    print(f"  {hdr}  ||  {stats}")
    print(f"  {'-'*88}")
    for r in rows:
        vals = " | ".join(f"{r[k]:>10}" for k in param_keys)
        print(f"  {vals}  ||"
              f"  {r['trades']:>4}  | {r['wr']:>6.1f}% | {r['pf']:>7.3f} |"
              f" {r['net_pct']:>+7.2f}% | {r['max_dd']:>6.2f}% | {r['calmar']:>6.3f} |"
              f" {r['tp']}/{r['sl']}/{r['mb']}")



# ─── Build indicators + signals once at defaults ───────────────────────────────
print("\nBuilding indicators & signals (default params) ...")
df_full, ls_full, ss_full = build_indicators(
    raw,
    adx_thresh=D_ADX_THRESH,
    pb_pct=D_PB_PCT,
    vol_mult=D_VOL_MULT,
    atr_floor=D_ATR_FLOOR
)
df_ytd  = df_full[df_full.index >= YTD_START].copy()
ls_ytd  = ls_full.reindex(df_ytd.index, fill_value=False)
ss_ytd  = ss_full.reindex(df_ytd.index, fill_value=False)
print(f"YTD bars: {len(df_ytd)}  |  default signals: {ss_ytd.sum()} short")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — Exit parameter sweep  (signals fixed)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("  STAGE 1 — Sweep TP×, SL×, max_bars  (signals fixed)")
print("═"*60)

s1_tp       = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
s1_sl       = [1.0, 1.5, 2.0, 2.5, 3.0]
s1_maxbars  = [0, 10, 15, 20, 25, 30]

s1_rows = []
total_s1 = len(s1_tp) * len(s1_sl) * len(s1_maxbars)
print(f"Combos: {total_s1}")

for tp, sl, mb in itertools.product(s1_tp, s1_sl, s1_maxbars):
    if tp <= sl:   # require positive R:R
        continue
    r = simulate(df_ytd, ls_ytd, ss_ytd,
                 sl_m=sl, tp_m=tp, trail_act=D_TRAIL_ACT,
                 trail_dist=D_TRAIL_DIST, max_bars=mb)
    if r is None:
        continue
    r.update({"tp_m": tp, "sl_m": sl, "max_bars": mb})
    s1_rows.append(r)

s1_best = top_n(s1_rows, 15, key="net_pct")
print_table(s1_best, ["tp_m","sl_m","max_bars"], "TOP 15 by net_pct — Stage 1 (exit params)")

# best combo for stage 2
b1 = s1_best[0]
BEST_TP = b1["tp_m"]; BEST_SL = b1["sl_m"]; BEST_MB = b1["max_bars"]
print(f"\n→ Stage-1 winner:  TP×{BEST_TP}  SL×{BEST_SL}  max_bars={BEST_MB}"
      f"  ({b1['trades']}T  WR={b1['wr']}%  PF={b1['pf']}  net={b1['net_pct']:+.2f}%)")

# Also save full Stage 1 results
s1_df = pd.DataFrame(s1_rows).sort_values("net_pct", ascending=False)
s1_df.to_csv("sweep_s1_exit_params.csv", index=False)
print("Stage-1 results → sweep_s1_exit_params.csv")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — Signal filter sweep  (exits from Stage-1 best)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("  STAGE 2 — Sweep ADX thresh, PB%, ATR floor, vol mult")
print(f"           Exits locked at TP×{BEST_TP} SL×{BEST_SL} max_bars={BEST_MB}")
print("═"*60)

s2_adx      = [12, 15, 18, 20, 25]
s2_pb       = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
s2_atrf     = [0.0, 0.0005, 0.0010, 0.0015]   # 0%, 0.05%, 0.10%, 0.15%
s2_vol      = [0.3, 0.5, 0.7, 1.0]

total_s2 = len(s2_adx) * len(s2_pb) * len(s2_atrf) * len(s2_vol)
print(f"Combos: {total_s2} (rebuilds signals each time)")

s2_rows = []
for adx, pb, atrf, vol in itertools.product(s2_adx, s2_pb, s2_atrf, s2_vol):
    df_f, ls_f, ss_f = build_indicators(
        raw,
        adx_thresh=adx,
        pb_pct=pb,
        vol_mult=vol,
        atr_floor=atrf
    )
    dy = df_f[df_f.index >= YTD_START].copy()
    if len(dy) == 0:
        continue
    ls_y = ls_f.reindex(dy.index, fill_value=False)
    ss_y = ss_f.reindex(dy.index, fill_value=False)
    r = simulate(dy, ls_y, ss_y,
                 sl_m=BEST_SL, tp_m=BEST_TP, trail_act=D_TRAIL_ACT,
                 trail_dist=D_TRAIL_DIST, max_bars=BEST_MB)
    if r is None:
        continue
    r.update({"adx": adx, "pb_pct": pb, "atr_floor": atrf, "vol_mult": vol})
    s2_rows.append(r)

s2_best = top_n(s2_rows, 15, key="net_pct")
print_table(s2_best, ["adx","pb_pct","atr_floor","vol_mult"], "TOP 15 by net_pct — Stage 2 (signal filters)")

b2 = s2_best[0]
BEST_ADX  = b2["adx"];   BEST_PB   = b2["pb_pct"]
BEST_ATRF = b2["atr_floor"]; BEST_VOL = b2["vol_mult"]
print(f"\n→ Stage-2 winner:  ADX={BEST_ADX}  PB={BEST_PB}%  ATR_floor={BEST_ATRF*100:.2f}%  vol×{BEST_VOL}"
      f"  ({b2['trades']}T  WR={b2['wr']}%  PF={b2['pf']}  net={b2['net_pct']:+.2f}%)")

s2_df = pd.DataFrame(s2_rows).sort_values("net_pct", ascending=False)
s2_df.to_csv("sweep_s2_signal_params.csv", index=False)
print("Stage-2 results → sweep_s2_signal_params.csv")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — Trail parameter sweep  (all other params from S1+S2)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("  STAGE 3 — Sweep trail_act, trail_dist")
print(f"           Exits: TP×{BEST_TP} SL×{BEST_SL} max_bars={BEST_MB}")
print(f"           Signals: ADX={BEST_ADX} PB={BEST_PB}% ATR_f={BEST_ATRF*100:.2f}% vol×{BEST_VOL}")
print("═"*60)

# Rebuild signals with Stage-2 best params
df_s3, ls_s3, ss_s3 = build_indicators(
    raw,
    adx_thresh=BEST_ADX,
    pb_pct=BEST_PB,
    vol_mult=BEST_VOL,
    atr_floor=BEST_ATRF
)
dy_s3 = df_s3[df_s3.index >= YTD_START].copy()
ls_s3y = ls_s3.reindex(dy_s3.index, fill_value=False)
ss_s3y = ss_s3.reindex(dy_s3.index, fill_value=False)
print(f"Signals for Stage-3: {ss_s3y.sum()} short")

s3_ta   = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 99.0]  # 99=effectively off
s3_td   = [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]
total_s3 = len(s3_ta) * len(s3_td)
print(f"Combos: {total_s3}")

s3_rows = []
for ta, td in itertools.product(s3_ta, s3_td):
    r = simulate(dy_s3, ls_s3y, ss_s3y,
                 sl_m=BEST_SL, tp_m=BEST_TP, trail_act=ta,
                 trail_dist=td, max_bars=BEST_MB)
    if r is None:
        continue
    r.update({"trail_act": ta, "trail_dist": td})
    s3_rows.append(r)

s3_best = top_n(s3_rows, 15, key="net_pct")
print_table(s3_best, ["trail_act","trail_dist"], "TOP 15 by net_pct — Stage 3 (trail params)")

b3 = s3_best[0]
BEST_TA = b3["trail_act"]; BEST_TD = b3["trail_dist"]
print(f"\n→ Stage-3 winner:  trail_act={BEST_TA}  trail_dist={BEST_TD}"
      f"  ({b3['trades']}T  WR={b3['wr']}%  PF={b3['pf']}  net={b3['net_pct']:+.2f}%)")

s3_df = pd.DataFrame(s3_rows).sort_values("net_pct", ascending=False)
s3_df.to_csv("sweep_s3_trail_params.csv", index=False)
print("Stage-3 results → sweep_s3_trail_params.csv")


# ══════════════════════════════════════════════════════════════════════════════
# FINAL VALIDATION — run full simulation with all best params
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("  FINAL VALIDATION — all best params combined")
print("═"*60)

df_fin, ls_fin, ss_fin = build_indicators(
    raw,
    adx_thresh=BEST_ADX,
    pb_pct=BEST_PB,
    vol_mult=BEST_VOL,
    atr_floor=BEST_ATRF
)
dy_fin = df_fin[df_fin.index >= YTD_START].copy()
ls_fin_y = ls_fin.reindex(dy_fin.index, fill_value=False)
ss_fin_y = ss_fin.reindex(dy_fin.index, fill_value=False)

r_fin = simulate(dy_fin, ls_fin_y, ss_fin_y,
                 sl_m=BEST_SL, tp_m=BEST_TP,
                 trail_act=BEST_TA, trail_dist=BEST_TD,
                 max_bars=BEST_MB)

print(f"""
  Optimised Parameters
  ───────────────────────────────────────────────────────
  ADX thresh   : {BEST_ADX}
  PB tolerance : {BEST_PB}%
  ATR floor    : {BEST_ATRF*100:.2f}%
  Vol mult     : {BEST_VOL}×
  SL mult      : {BEST_SL}×ATR
  TP mult      : {BEST_TP}×ATR  (R:R = 1:{BEST_TP/BEST_SL:.2f})
  Trail act    : {BEST_TA}×ATR
  Trail dist   : {BEST_TD}×ATR
  Max bars     : {BEST_MB}

  Final Results (YTD {YTD_START.year})
  ───────────────────────────────────────────────────────
  Trades  : {r_fin['trades']}  (TP:{r_fin['tp']}  SL:{r_fin['sl']}  MB:{r_fin['mb']})
  Win rate: {r_fin['wr']:.1f}%
  Prof fac: {r_fin['pf']:.3f}
  Net P&L : {r_fin['net_pct']:+.2f}%
  Max DD  : {r_fin['max_dd']:.2f}%
  Calmar  : {r_fin['calmar']:.3f}
  ───────────────────────────────────────────────────────
  (baseline was: 13T  WR=7.7%  PF=0.074  net=-9.89%)
""")
