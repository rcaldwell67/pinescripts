# APM v3  —  CLM refined sweep  (session filter + tighter grid)  15m ONLY
# ─────────────────────────────────────────────────────────────────────────────
import subprocess, sys
for pkg in ["yfinance", "pandas", "numpy", "pytz"]:
    try: import importlib; importlib.import_module(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import itertools, warnings, pytz
warnings.filterwarnings("ignore")

TICKER      = "CLM"
INTERVAL    = "15m"        # ← 15m only
INITIAL_CAP = 10_000.0
COMM        = 0.0006
PANIC_MULT  = 1.3
EMA_FAST    = 21;  EMA_MID = 50;  EMA_SLOW = 200
ADX_LEN     = 14;  RSI_LEN = 14;  VOL_LEN  = 20
VOL_MULT    = 1.2; MIN_BODY = 0.20
RSI_LO_S = 32; RSI_HI_S = 58
TRAIL_ACT   = 2.5
ET = pytz.timezone("America/New_York")

# ── Session hour bounds (ET local hour) ───────────────────────────────────────
#   "all"          – no filter
#   "morning_only" – entries 9:30–11:59 AM ET
#   "close_only"   – entries 2:00–3:59 PM ET (pre-close bracket)
#   "no_overnight" – any entry hour; force-close open positions at EOD
SESSION_RULES = {
    "all":          lambda h: True,
    "morning_only": lambda h: 9 <= h < 12,
    "close_only":   lambda h: 14 <= h < 16,
}

# ── Indicators ────────────────────────────────────────────────────────────────
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def sma(s, n): return s.rolling(n).mean()

def rsi_calc(s, n):
    d = s.diff()
    g  = d.clip(lower=0).rolling(n).mean()
    ls = (-d).clip(lower=0).rolling(n).mean()
    return 100 - 100 / (1 + g / ls.replace(0, np.nan))

def atr_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def adx_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    up  = h.diff(); dn  = -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr  = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    at  = tr.rolling(n).mean()
    pdi = pd.Series(pdm, index=h.index).rolling(n).mean() / at * 100
    ndi = pd.Series(ndm, index=h.index).rolling(n).mean() / at * 100
    dx  = ((pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan) * 100)
    return pdi, ndi, dx.rolling(n).mean()

# ── Download & enrich 15m data ────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} ...")
raw = yf.download(TICKER, period="60d", interval=INTERVAL,
                  auto_adjust=True, progress=False)
raw.columns = raw.columns.get_level_values(0)
raw.index   = pd.to_datetime(raw.index, utc=True)
raw.sort_index(inplace=True)
raw = raw[raw["Volume"] > 0].copy()

raw["EMA_FAST"] = ema(raw["Close"], EMA_FAST)
raw["EMA_MID"]  = ema(raw["Close"], EMA_MID)
raw["EMA_SLOW"] = ema(raw["Close"], EMA_SLOW)
raw["RSI"]      = rsi_calc(raw["Close"], RSI_LEN)
raw["ATR"]      = atr_calc(raw, ADX_LEN)
raw["ATR_BL"]   = sma(raw["ATR"], 60)
raw["VOL_MA"]   = sma(raw["Volume"], VOL_LEN)
raw["DI_PLUS"], raw["DI_MINUS"], raw["ADX"] = adx_calc(raw, ADX_LEN)
raw.dropna(inplace=True)

raw["ET_hour"] = raw.index.tz_convert(ET).hour
raw_et         = raw.index.tz_convert(ET)
raw["trading_date"] = raw_et.date
last_bar_idx   = raw.groupby("trading_date").apply(lambda g: g.index[-1])
raw["is_eod_bar"] = raw.index.isin(last_bar_idx.values)

print(f"  {len(raw)} rows after warmup\n")

# ── Pre-compute fixed signal masks ────────────────────────────────────────────
sig = {}
sig["full_bear"]  = (raw["EMA_FAST"] < raw["EMA_MID"]) & (raw["EMA_MID"] < raw["EMA_SLOW"])
sig["slope_down"] = raw["EMA_FAST"] < raw["EMA_FAST"].shift(3)
sig["rsi_fall"]   = raw["RSI"] < raw["RSI"].shift(1)
sig["rsi_ok_s"]   = (raw["RSI"] >= RSI_LO_S) & (raw["RSI"] <= RSI_HI_S)
sig["vol_ok"]     = raw["Volume"] >= raw["VOL_MA"] * VOL_MULT
sig["is_panic"]   = raw["ATR"] > raw["ATR_BL"] * PANIC_MULT
sig["body_size"]  = (raw["Close"] - raw["Open"]).abs() / raw["ATR"]

# ── Simulation ────────────────────────────────────────────────────────────────
def run_sim(adx_thresh, sl_m, tp_m, trail_dist, pb_pct,
            session_filter, risk_pct, no_overnight=False):

    hour_gate = SESSION_RULES.get(session_filter, lambda h: True)

    pb_tol_dn = raw["EMA_FAST"].shift(1) * (1.0 - pb_pct / 100.0)
    short_pb  = (raw["High"].shift(1) >= pb_tol_dn) & \
                (raw["Close"] < raw["EMA_FAST"]) & \
                (raw["Close"] < raw["Open"]) & (sig["body_size"] >= MIN_BODY)

    adx_ok     = raw["ADX"] > adx_thresh
    base_short = (~sig["is_panic"] & adx_ok & sig["full_bear"] &
                  sig["slope_down"] & sig["rsi_fall"] & sig["rsi_ok_s"] &
                  sig["vol_ok"] & short_pb)

    eq  = INITIAL_CAP
    pos = None
    pnls = []

    for ts, row in raw.iterrows():
        cl = float(row["Close"]); hi = float(row["High"])
        lo = float(row["Low"]);   av = float(row["ATR"])
        et_h   = int(row["ET_hour"])
        is_eod = bool(row["is_eod_bar"])

        hit_tp = hit_sl = force_exit = False

        if pos is not None:
            pos["best"] = min(pos["best"], lo)
            if pos["best"] <= pos["entry"] - av * TRAIL_ACT:
                pos["sl"] = min(pos["sl"], pos["best"] + av * trail_dist)
            hit_tp     = lo <= pos["tp"]
            hit_sl     = hi >= pos["sl"]
            force_exit = no_overnight and is_eod and not hit_tp and not hit_sl

        if hit_tp or hit_sl or force_exit:
            xp      = cl if force_exit else (pos["tp"] if hit_tp else pos["sl"])
            raw_ret = (pos["entry"] - xp) / pos["entry"]
            comm    = pos["notional"] * COMM * 2
            dpnl    = raw_ret * pos["notional"] - comm
            eq     += dpnl
            pnls.append(dpnl)
            pos     = None

        if pos is None and bool(base_short[ts]) and hour_gate(et_h):
            sd   = av * sl_m
            not_ = min(eq * risk_pct / sd * cl, eq * 5.0)
            sl   = cl + sd
            tp   = cl - av * tp_m
            pos  = {"entry": cl, "sl": sl, "tp": tp, "best": cl, "notional": not_}

    if not pnls: return None
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr     = len(wins) / len(pnls) * 100
    pf     = (sum(wins) / abs(sum(losses))
              if losses and sum(losses) != 0 else float("inf"))
    ret    = (eq / INITIAL_CAP - 1) * 100

    pk = INITIAL_CAP; mdd = 0.0; run_eq = INITIAL_CAP
    for p in pnls:
        run_eq += p
        if run_eq > pk: pk = run_eq
        dd = (run_eq - pk) / pk * 100
        if dd < mdd: mdd = dd

    return dict(trades=len(pnls), wr=wr, pf=pf, ret=ret, mdd=mdd)

# ── Sweep grid ─────────────────────────────────────────────────────────────────
session_filters = {
    "all":          (False,),
    "morning_only": (False,),
    "close_only":   (False,),
    "no_overnight": (True,),
}
adx_threshes = [12, 15, 18, 20, 22, 25]
tp_mults     = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
sl_mults     = [1.5, 2.0, 2.5, 3.0, 3.5]
pb_pcts      = [0.20, 0.30, 0.40, 0.50]
trail_dists  = [0.4, 0.6, 1.0]
risk_pcts    = [0.010, 0.015, 0.020]

total = (len(session_filters) * len(adx_threshes) * len(tp_mults) *
         len(sl_mults) * len(pb_pcts) * len(trail_dists) * len(risk_pcts))
print(f"Refined sweep: {total:,} combinations  (shorts_only, {INTERVAL})")

results = []
done = 0
for sf, (no_ov,) in session_filters.items():
    for adx_t, tp_m, sl_m, pb, td, rp in itertools.product(
            adx_threshes, tp_mults, sl_mults, pb_pcts, trail_dists, risk_pcts):
        r = run_sim(adx_t, sl_m, tp_m, td, pb, sf, rp, no_overnight=no_ov)
        if r is not None:
            results.append({"session": sf, "adx": adx_t, "tp": tp_m, "sl": sl_m,
                            "pb_pct": pb, "trail_dist": td, "risk_pct": rp, **r})
        done += 1
        if done % 5000 == 0:
            print(f"  {done:,}/{total:,} …")

print(f"  {done:,}/{total:,} — complete\n")

rdf = pd.DataFrame(results)
if rdf.empty:
    print("No results."); sys.exit(1)

MIN_TRADES = 8
rdf_all = rdf.copy()
rdf = rdf[rdf["trades"] >= MIN_TRADES].copy()
print(f"Combinations with ≥{MIN_TRADES} trades: {len(rdf):,}")

viable = rdf[(rdf["ret"] > 0) & (rdf["mdd"] > -20)].copy()
print(f"Profitable + MDD>-20%: {len(viable):,}\n")

if viable.empty:
    print("No viable combos found.")
    sys.exit(0)

top = viable.sort_values(["ret","pf"], ascending=False).head(20)
print("── Top 20 by Return ─────────────────────────────────────────────────")
print(top[["session","adx","tp","sl","pb_pct","trail_dist","risk_pct",
           "trades","wr","pf","ret","mdd"]].to_string(index=False, float_format="{:.2f}".format))

top_pf = viable.sort_values(["pf","ret"], ascending=False).head(10)
print("\n── Top 10 by Profit Factor ──────────────────────────────────────────")
print(top_pf[["session","adx","tp","sl","pb_pct","trail_dist","risk_pct",
              "trades","wr","pf","ret","mdd"]].to_string(index=False, float_format="{:.2f}".format))

viable["score"] = (viable["ret"]    / viable["ret"].max()           * 0.5 +
                   viable["pf"]     / viable["pf"].max()            * 0.3 +
                   viable["trades"] / viable["trades"].max()         * 0.1 -
                   viable["mdd"].abs() / viable["mdd"].abs().max()  * 0.1)
best = viable.sort_values("score", ascending=False).iloc[0]
print(f"""
── Best balanced combination ────────────────────────────────────
  Session filter : {best['session']}
  ADX threshold  : {best['adx']}
  TP multiplier  : {best['tp']}
  SL multiplier  : {best['sl']}
  PB tolerance   : {best['pb_pct']}%
  Trail distance : {best['trail_dist']}
  Risk per trade : {best['risk_pct']*100:.1f}%
  ─────────────────
  Trades         : {best['trades']}
  Win rate       : {best['wr']:.1f}%
  Profit factor  : {best['pf']:.3f}
  Return         : {best['ret']:.2f}%
  Max drawdown   : {best['mdd']:.2f}%
""")

print("\n── Mean stats by session filter (viable combos) ──────────────────────")
by_sess = viable.groupby("session")[["trades","wr","pf","ret","mdd"]].mean().round(2)
print(by_sess.to_string())

out_path = "sweep_clm_refined_results.csv"
rdf_all.sort_values("ret", ascending=False).to_csv(out_path, index=False)
print(f"\nFull results → {out_path}")
