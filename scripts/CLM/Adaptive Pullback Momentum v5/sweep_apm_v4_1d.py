"""FAST parameter sweep for APM v4.1 — CLM 1D
Sweeps key parameters and ranks results by Profit Factor.
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
from itertools import product
warnings.filterwarnings("ignore")

# ── Fixed config ───────────────────────────────────────────────────────────────
TICKER     = "CLM"
INTERVAL   = "1d"
PERIOD     = "max"
INIT_CAP   = 10_000.0
COMMISSION = 0.0006
RISK_PCT   = 0.01
MIN_TRADES = 10

# ── Download data once ─────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} {PERIOD} …")
raw = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                  auto_adjust=True, progress=False)
raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
df_raw = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()
df_raw.index = pd.to_datetime(df_raw.index)
print(f"  Rows: {len(df_raw)}  |  {df_raw.index[0].date()} → {df_raw.index[-1].date()}")

# ── Indicator helpers ──────────────────────────────────────────────────────────
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    u = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    v = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + u / v.replace(0, np.nan))

def atr_series(h, l, c, n=14):
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def adx_series(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr14 = atr_series(h, l, c, n)
    pdi = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    ndi = 100 * ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    dx  = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()

def di_series(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr14 = atr_series(h, l, c, n)
    pdi = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    ndi = 100 * ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    return pdi, ndi

# ── Pre-compute indicators that don't change across the sweep ──────────────────
# These depend on EMA_FAST, EMA_MID, EMA_SLOW, ADX_LEN, ATR_LEN, RSI_LEN, VOL_MA_LEN
# We'll recompute per-combo only for the varying params.
# For speed, pre-cache indicator sets for each unique (ema_fast,ema_mid,ema_slow,adx_len,atr_len,rsi_len,vol_len)

from functools import lru_cache

ATR_BL_LEN = 60

def build_indicators(df, ema_f, ema_m, ema_s, adx_len, atr_len, rsi_len, vol_len):
    d = df.copy()
    d["EMA_F"]  = ema(d["Close"], ema_f)
    d["EMA_M"]  = ema(d["Close"], ema_m)
    d["EMA_S"]  = ema(d["Close"], ema_s)
    d["ATR"]    = atr_series(d["High"], d["Low"], d["Close"], atr_len)
    d["ATR_BL"] = d["ATR"].rolling(ATR_BL_LEN).mean()
    d["ADX"]    = adx_series(d["High"], d["Low"], d["Close"], adx_len)
    d["RSI"]    = rsi(d["Close"], rsi_len)
    d["VOL_MA"] = d["Volume"].rolling(vol_len).mean()
    d["BODY"]   = (d["Close"] - d["Open"]).abs() / d["ATR"].replace(0, np.nan)
    return d

def run_backtest(df, params):
    (EMA_F, EMA_M, EMA_S, ADX_LEN, ADX_THRESH, ATR_LEN, RSI_LEN, VOL_LEN,
     PB_PCT, VOL_MULT, MIN_BODY, PANIC_MULT,
     SL_MULT, TP_MULT, TRAIL_ACT, TRAIL_DIST,
     RSI_LO_L, RSI_HI_L, RSI_LO_S, RSI_HI_S,
     TRADE_LONGS, TRADE_SHORTS) = params

    d = build_indicators(df, EMA_F, EMA_M, EMA_S, ADX_LEN, ATR_LEN, RSI_LEN, VOL_LEN)

    pb_tol_up = d["EMA_F"].shift(1) * (1.0 + PB_PCT / 100.0)
    pb_tol_dn = d["EMA_F"].shift(1) * (1.0 - PB_PCT / 100.0)

    long_pb  = (d["Low"].shift(1) <= pb_tol_up) & (d["Close"] > d["EMA_F"]) & \
               (d["Close"] > d["Open"]) & (d["BODY"] >= MIN_BODY)
    short_pb = (d["High"].shift(1) >= pb_tol_dn) & (d["Close"] < d["EMA_F"]) & \
               (d["Close"] < d["Open"]) & (d["BODY"] >= MIN_BODY)

    is_trending = d["ADX"] > ADX_THRESH
    is_panic    = d["ATR"] > d["ATR_BL"] * PANIC_MULT

    long_entry = (
        TRADE_LONGS & long_pb &
        (d["Close"] > d["EMA_S"]) & (d["EMA_F"] > d["EMA_M"]) &
        (d["RSI"] >= RSI_LO_L) & (d["RSI"] <= RSI_HI_L) &
        (d["Volume"] >= d["VOL_MA"] * VOL_MULT) &
        is_trending & ~is_panic
    )
    short_entry = (
        TRADE_SHORTS & short_pb &
        (d["Close"] < d["EMA_S"]) & (d["EMA_F"] < d["EMA_M"]) &
        (d["RSI"] >= RSI_LO_S) & (d["RSI"] <= RSI_HI_S) &
        (d["Volume"] >= d["VOL_MA"] * VOL_MULT) &
        is_trending & ~is_panic
    )

    equity = INIT_CAP
    in_trade = False
    direction = None
    entry_px = sl_price = tp_price = best_price = entry_atr = qty = 0.0
    entry_time = None

    trades = []
    equity_curve = [equity]
    win_count = closed_count = 0
    trail_active_f = False
    max_runup_f = 0.0
    bar_index_map = {t: i for i, t in enumerate(d.index)}

    l_e = long_entry.values
    s_e = short_entry.values
    o = d["Open"].values
    h = d["High"].values
    l_ = d["Low"].values
    c = d["Close"].values
    atr_v = d["ATR"].values
    idx = d.index

    for i in range(len(d)):
        ca = atr_v[i]
        if np.isnan(ca) or ca == 0:
            equity_curve.append(equity); continue

        exited = False
        if in_trade:
            if direction == "long":
                if h[i] > best_price: best_price = h[i]
                max_runup_f = max(max_runup_f, best_price - entry_px)
                if best_price >= entry_px + entry_atr * TRAIL_ACT:
                    t = best_price - entry_atr * TRAIL_DIST
                    if t > sl_price: sl_price = t
                    trail_active_f = True
                if l_[i] <= sl_price:
                    ep = min(o[i], sl_price); pnl = (ep - entry_px) * qty
                    comm = (entry_px + ep) * qty * COMMISSION
                    net_pnl = pnl - comm; equity += net_pnl
                    closed_count += 1
                    if net_pnl > 0: win_count += 1
                    trades.append(net_pnl); in_trade = False; exited = True
                elif h[i] >= tp_price:
                    ep = max(o[i], tp_price); pnl = (ep - entry_px) * qty
                    comm = (entry_px + ep) * qty * COMMISSION
                    net_pnl = pnl - comm; equity += net_pnl
                    closed_count += 1
                    if net_pnl > 0: win_count += 1
                    trades.append(net_pnl); in_trade = False; exited = True
            else:
                if l_[i] < best_price: best_price = l_[i]
                max_runup_f = max(max_runup_f, entry_px - best_price)
                if best_price <= entry_px - entry_atr * TRAIL_ACT:
                    t = best_price + entry_atr * TRAIL_DIST
                    if t < sl_price: sl_price = t
                    trail_active_f = True
                if h[i] >= sl_price:
                    ep = max(o[i], sl_price); pnl = (entry_px - ep) * qty
                    comm = (entry_px + ep) * qty * COMMISSION
                    net_pnl = pnl - comm; equity += net_pnl
                    closed_count += 1
                    if net_pnl > 0: win_count += 1
                    trades.append(net_pnl); in_trade = False; exited = True
                elif l_[i] <= tp_price:
                    ep = min(o[i], tp_price); pnl = (entry_px - ep) * qty
                    comm = (entry_px + ep) * qty * COMMISSION
                    net_pnl = pnl - comm; equity += net_pnl
                    closed_count += 1
                    if net_pnl > 0: win_count += 1
                    trades.append(net_pnl); in_trade = False; exited = True

        if not in_trade:
            if l_e[i]:
                sd = ca * SL_MULT; entry_px = c[i]; sl_price = entry_px - sd
                tp_price = entry_px + ca * TP_MULT; entry_atr = ca
                best_price = entry_px; qty = equity * RISK_PCT / sd
                entry_time = idx[i]; direction = "long"; in_trade = True
                trail_active_f = False; max_runup_f = 0.0
            elif s_e[i]:
                sd = ca * SL_MULT; entry_px = c[i]; sl_price = entry_px + sd
                tp_price = entry_px - ca * TP_MULT; entry_atr = ca
                best_price = entry_px; qty = equity * RISK_PCT / sd
                entry_time = idx[i]; direction = "short"; in_trade = True
                trail_active_f = False; max_runup_f = 0.0

        equity_curve.append(equity)

    if len(trades) < MIN_TRADES:
        return None

    arr = np.array(trades)
    wins = arr[arr > 0]; losses = arr[arr <= 0]
    gp = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0
    pf = gp / gl if gl > 0 else float("inf")
    wr = len(wins) / len(arr) * 100
    net = arr.sum()
    net_pct = net / INIT_CAP * 100
    eq_arr = np.array(equity_curve)
    roll_max = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - roll_max) / roll_max * 100).min()

    return {
        "pf": pf, "wr": wr, "net_pct": net_pct, "trades": len(arr),
        "dd": dd, "avg_w": wins.mean() if len(wins) else 0,
        "avg_l": losses.mean() if len(losses) else 0,
    }

# ── Sweep grid ─────────────────────────────────────────────────────────────────
# Focus on the parameters with highest leverage on profitability
sweep = {
    "ema_mid":     [34, 50],
    "adx_thresh":  [20, 25, 28, 33],
    "pb_pct":      [0.10, 0.15, 0.20, 0.30],
    "min_body":    [0.10, 0.20, 0.30],
    "panic_mult":  [1.5, 2.0, 2.5],
    "sl_mult":     [1.5, 2.0, 2.5],
    "tp_mult":     [1.5, 2.0, 2.5, 3.0],
    "trail_act":   [1.5, 2.0, 3.0],
    "trail_dist":  [0.4, 0.6, 0.8],
    "rsi_lo_l":    [38, 42],
    "rsi_hi_l":    [68, 72, 78],
    "rsi_lo_s":    [28, 32],
    "rsi_hi_s":    [58, 62],
    "vol_mult":    [0.8, 1.0, 1.2],
}

# Fixed across sweep
EMA_FAST  = 21
EMA_SLOW  = 200
ADX_LEN   = 14
ATR_LEN   = 14
RSI_LEN   = 14
VOL_LEN   = 20

results = []
keys = list(sweep.keys())
combos = list(product(*[sweep[k] for k in keys]))
total = len(combos)
print(f"\nSweeping {total:,} combinations …")

for n, combo in enumerate(combos):
    if n % 5000 == 0:
        print(f"  {n:>7,}/{total:,}  ({n/total*100:.1f}%)", flush=True)

    p = dict(zip(keys, combo))
    params = (
        EMA_FAST, p["ema_mid"], EMA_SLOW,
        ADX_LEN, p["adx_thresh"], ATR_LEN, RSI_LEN, VOL_LEN,
        p["pb_pct"], p["vol_mult"], p["min_body"], p["panic_mult"],
        p["sl_mult"], p["tp_mult"], p["trail_act"], p["trail_dist"],
        p["rsi_lo_l"], p["rsi_hi_l"], p["rsi_lo_s"], p["rsi_hi_s"],
        True, True,
    )
    r = run_backtest(df_raw, params)
    if r is None:
        continue
    if r["pf"] > 1.0 and r["net_pct"] > 0:
        results.append({**p, **r})

print(f"\nDone. {len(results)} profitable combos found (≥{MIN_TRADES} trades, PF>1.0).\n")

if not results:
    print("No profitable combos found — try relaxing MIN_TRADES or expanding the grid.")
else:
    rdf = pd.DataFrame(results).sort_values("pf", ascending=False)

    print("=" * 90)
    print(f"  TOP 20 by Profit Factor  (min {MIN_TRADES} trades, PF>1.0, net>0)")
    print("=" * 90)
    cols = ["pf", "wr", "net_pct", "trades", "dd",
            "adx_thresh", "pb_pct", "tp_mult", "sl_mult",
            "trail_act", "trail_dist", "min_body", "panic_mult",
            "ema_mid", "rsi_lo_l", "rsi_hi_l", "rsi_lo_s", "rsi_hi_s", "vol_mult"]
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", "{:.3f}".format)
    print(rdf[cols].head(20).to_string(index=False))

    best = rdf.iloc[0]
    print(f"\n{'='*60}")
    print(f"  BEST COMBO")
    print(f"{'='*60}")
    print(f"  EMA fast/mid/slow : 21 / {int(best['ema_mid'])} / 200")
    print(f"  ADX thresh        : {best['adx_thresh']}")
    print(f"  Pullback tol (%)  : {best['pb_pct']}")
    print(f"  Min body (xATR)   : {best['min_body']}")
    print(f"  Panic mult        : {best['panic_mult']}")
    print(f"  SL mult           : {best['sl_mult']}")
    print(f"  TP mult           : {best['tp_mult']}")
    print(f"  Trail act / dist  : {best['trail_act']} / {best['trail_dist']}")
    print(f"  RSI Long          : {best['rsi_lo_l']} - {best['rsi_hi_l']}")
    print(f"  RSI Short         : {best['rsi_lo_s']} - {best['rsi_hi_s']}")
    print(f"  Vol mult          : {best['vol_mult']}")
    print(f"  ─────────────────────────────────")
    print(f"  Profit Factor     : {best['pf']:.3f}")
    print(f"  Win Rate          : {best['wr']:.1f}%")
    print(f"  Net Return        : {best['net_pct']:+.2f}%")
    print(f"  Trades            : {int(best['trades'])}")
    print(f"  Max Drawdown      : {best['dd']:.2f}%")
    print(f"{'='*60}")

    rdf.to_csv("sweep_apm_v4_1d_results.csv", index=False)
    print(f"\nFull results saved → sweep_apm_v4_1d_results.csv")
