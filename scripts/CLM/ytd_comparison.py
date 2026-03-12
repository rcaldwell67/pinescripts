"""
CLM APM v1–v5  ·  Year-To-Date Comparison (2026-01-01 → today)
=================================================================
Downloads data for each strategy's timeframe, computes all indicators
on full available history (for proper EMA/ADX warmup), then runs each
strategy's bar-by-bar simulation from scratch starting at YTD_START
with $10,000 capital.  Prints a single comparison table at the end.

Strategies
  v1  — CLM 15m  · Shorts only · session 9–12 · full filter suite
  v2  — CLM 30m  · Shorts only · no session   · full filter suite
  v3  — CLM  1h  · Longs+Shorts· no session   · simplified filters
  v4  — CLM  1d  · Longs only  · no session   · EMA-mid slope filter
  v5  — CLM 10m  · Shorts only · session 9–14 · Stage-3 params
"""

import subprocess, sys
for pkg in ["yfinance", "pandas", "numpy", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
import warnings
warnings.filterwarnings("ignore")

TICKER         = "CLM"
YTD_START      = pd.Timestamp("2026-01-01", tz="America/New_York")
INITIAL_CAP    = 10_000.0
COMMISSION_PCT = 0.0006
RISK_PCT       = 0.01
_ET            = pytz.timezone("America/New_York")

# ── Shared indicator helpers ───────────────────────────────────────────────────
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def atr_series(h, l, c, n):
    hl  = h - l
    hpc = (h - c.shift(1)).abs()
    lpc = (l - c.shift(1)).abs()
    return pd.concat([hl, hpc, lpc], axis=1).max(axis=1).ewm(alpha=1/n, adjust=False).mean()

def rsi_series(c, n):
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - (100 / (1 + g / l.replace(0, 1e-10)))

def adx_dmi(h, l, c, n):
    up = h - h.shift(1);  dn = l.shift(1) - l
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a   = atr_series(h, l, c, n)
    sp  = pd.Series(pdm, index=h.index).ewm(alpha=1/n, adjust=False).mean()
    sm  = pd.Series(ndm, index=h.index).ewm(alpha=1/n, adjust=False).mean()
    dip = 100 * sp / a.replace(0, 1e-10)
    dim = 100 * sm / a.replace(0, 1e-10)
    dx  = 100 * (dip - dim).abs() / (dip + dim).replace(0, 1e-10)
    adx = dx.ewm(alpha=1/n, adjust=False).mean()
    return adx, dip, dim

def add_indicators(df, ema_fast=21, ema_mid=50, ema_slow=200,
                   atr_n=14, adx_n=14, rsi_n=14, vol_n=20, atr_bl_n=60):
    df["EF"]  = ema(df["Close"], ema_fast)
    df["EM"]  = ema(df["Close"], ema_mid)
    df["ES"]  = ema(df["Close"], ema_slow)
    df["ATR"] = atr_series(df["High"], df["Low"], df["Close"], atr_n)
    df["ATR_BL"] = df["ATR"].rolling(atr_bl_n).mean()
    df["ADX"], df["DI+"], df["DI-"] = adx_dmi(df["High"], df["Low"], df["Close"], adx_n)
    df["RSI"] = rsi_series(df["Close"], rsi_n)
    df["VOL_MA"] = df["Volume"].rolling(vol_n).mean()
    df["BODY"] = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, 1e-10)
    df.dropna(inplace=True)
    return df

# ── Generic bar-by-bar simulator ──────────────────────────────────────────────
def sim(df_ytd, long_sig, short_sig, cfg):
    """
    cfg keys: sl, tp, trail_act, trail_dist, max_bars, panic_mult,
              consec_limit, consec_cool
    Returns dict of performance metrics.
    """
    sl_m    = cfg["sl"];        tp_m    = cfg["tp"]
    ta      = cfg["trail_act"]; td      = cfg["trail_dist"]
    max_b   = cfg.get("max_bars", 0)
    cl_lim  = cfg.get("consec_limit", 2)
    cl_cool = cfg.get("consec_cool", 1)

    H  = df_ytd["High"].values;   L  = df_ytd["Low"].values
    C  = df_ytd["Close"].values;  AT = df_ytd["ATR"].values
    LS = long_sig.values;         SS = short_sig.values
    N  = len(df_ytd)

    equity   = INITIAL_CAP
    pos      = None
    pnls     = []
    eq_list  = []
    consec   = 0
    cooldown = 0
    trade_log = []  # (entry_time, exit_time, dir, pnl_pct, result)

    for i in range(N):
        atr_i = AT[i]
        if np.isnan(atr_i) or atr_i == 0:
            eq_list.append(equity); continue

        if pos is not None:
            d = pos["dir"]
            if d == "long":
                if H[i] > pos["best"]: pos["best"] = H[i]
                if pos["best"] >= pos["entry"] + atr_i * ta:
                    new_sl = pos["best"] - atr_i * td
                    if new_sl > pos["sl"]: pos["sl"] = new_sl
                # max bars
                if max_b > 0 and pos["bars"] >= max_b:
                    xp = C[i]; dp = _pnl(d, pos["entry"], xp, pos["notl"])
                    equity += dp; pnls.append(dp)
                    trade_log.append((pos["et"], df_ytd.index[i], d,
                                      (xp-pos["entry"])/pos["entry"]*100, "MB"))
                    _upd_consec(dp, consec, cl_lim, cl_cool,
                                consec_ref=[consec], cool_ref=[cooldown])
                    consec, cooldown = _cc(dp, consec, cooldown, cl_lim, cl_cool)
                    pos = None; eq_list.append(equity); continue
                pos["bars"] += 1
                htp = H[i] >= pos["tp"]; hsl = L[i] <= pos["sl"]
                if htp or hsl:
                    xp = pos["tp"] if htp else pos["sl"]
                    dp = _pnl(d, pos["entry"], xp, pos["notl"])
                    equity += dp; pnls.append(dp)
                    trade_log.append((pos["et"], df_ytd.index[i], d,
                                      (xp-pos["entry"])/pos["entry"]*100,
                                      "TP" if htp else "SL"))
                    consec, cooldown = _cc(dp, consec, cooldown, cl_lim, cl_cool)
                    pos = None
            else:  # short
                if L[i] < pos["best"]: pos["best"] = L[i]
                if pos["best"] <= pos["entry"] - atr_i * ta:
                    new_sl = pos["best"] + atr_i * td
                    if new_sl < pos["sl"]: pos["sl"] = new_sl
                # max bars
                if max_b > 0 and pos["bars"] >= max_b:
                    xp = C[i]; dp = _pnl(d, pos["entry"], xp, pos["notl"])
                    equity += dp; pnls.append(dp)
                    trade_log.append((pos["et"], df_ytd.index[i], d,
                                      (pos["entry"]-xp)/pos["entry"]*100, "MB"))
                    consec, cooldown = _cc(dp, consec, cooldown, cl_lim, cl_cool)
                    pos = None; eq_list.append(equity); continue
                pos["bars"] += 1
                htp = L[i] <= pos["tp"]; hsl = H[i] >= pos["sl"]
                if htp or hsl:
                    xp = pos["tp"] if htp else pos["sl"]
                    dp = _pnl(d, pos["entry"], xp, pos["notl"])
                    equity += dp; pnls.append(dp)
                    trade_log.append((pos["et"], df_ytd.index[i], d,
                                      (pos["entry"]-xp)/pos["entry"]*100,
                                      "TP" if htp else "SL"))
                    consec, cooldown = _cc(dp, consec, cooldown, cl_lim, cl_cool)
                    pos = None

        if pos is None:
            if cooldown > 0: cooldown -= 1
            elif LS[i] or SS[i]:
                d    = "long" if LS[i] else "short"
                sd   = atr_i * sl_m
                notl = min(equity * RISK_PCT / sd * C[i], equity * 5.0)
                if d == "long":
                    pos = {"dir": d, "entry": C[i], "best": C[i], "notl": notl,
                           "sl": C[i] - sd, "tp": C[i] + atr_i * tp_m,
                           "et": df_ytd.index[i], "bars": 0}
                else:
                    pos = {"dir": d, "entry": C[i], "best": C[i], "notl": notl,
                           "sl": C[i] + sd, "tp": C[i] - atr_i * tp_m,
                           "et": df_ytd.index[i], "bars": 0}
        eq_list.append(equity)

    if not pnls:
        return {"trades": 0, "wr": 0, "pf": 0, "net_pct": 0,
                "max_dd": 0, "calmar": 0, "longs": 0, "shorts": 0,
                "tp_exits": 0, "sl_exits": 0, "mb_exits": 0}

    arr  = np.array(pnls)
    wins = arr[arr > 0]; losses = arr[arr <= 0]
    net  = arr.sum(); net_pct = net / INITIAL_CAP * 100
    gp   = wins.sum() if len(wins) else 0
    gl   = abs(losses.sum()) if len(losses) else 0
    pf   = gp/gl if gl > 0 else float("inf")
    eq_a = np.array(eq_list)
    rm   = np.maximum.accumulate(eq_a)
    dd   = ((eq_a - rm) / rm * 100).min()
    calmar = net_pct / abs(dd) if dd < 0 else float("inf")

    longs  = sum(1 for t in trade_log if t[2] == "long")
    shorts = sum(1 for t in trade_log if t[2] == "short")
    tps    = sum(1 for t in trade_log if t[4] == "TP")
    sls    = sum(1 for t in trade_log if t[4] == "SL")
    mbs    = sum(1 for t in trade_log if t[4] == "MB")

    return {"trades": len(arr), "wr": round(len(wins)/len(arr)*100, 1),
            "pf": round(pf, 3), "net_pct": round(net_pct, 2),
            "max_dd": round(dd, 2), "calmar": round(calmar, 3),
            "longs": longs, "shorts": shorts,
            "tp_exits": tps, "sl_exits": sls, "mb_exits": mbs}

def _pnl(direction, entry, xp, notl):
    raw = (xp - entry)/entry if direction == "long" else (entry - xp)/entry
    return raw * notl - notl * COMMISSION_PCT * 2

def _cc(dp, consec, cooldown, cl_lim, cl_cool):
    if dp <= 0:
        consec += 1
        if consec >= cl_lim: cooldown = cl_cool; consec = 0
    else:
        consec = 0
    return consec, cooldown

def _upd_consec(*args): pass  # unused placeholder

# ── Data loaders ──────────────────────────────────────────────────────────────
def load_intraday(interval, period="60d"):
    raw = yf.download(TICKER, period=period, interval=interval,
                      auto_adjust=True, progress=False)
    if raw.empty: raise SystemExit(f"No {interval} data for {TICKER}")
    if isinstance(raw.columns, pd.MultiIndex): raw.columns = raw.columns.droplevel(1)
    raw = raw[["Open","High","Low","Close","Volume"]].copy()
    raw = raw[raw["Volume"] > 0].dropna()
    raw.index = pd.to_datetime(raw.index)
    if raw.index.tzinfo is None: raw.index = raw.index.tz_localize("UTC")
    return raw

def load_10m():
    raw5 = load_intraday("5m", period="60d")
    raw5_et = raw5.copy()
    raw5_et.index = raw5_et.index.tz_convert(_ET)
    df = raw5_et.resample("10min", label="left", closed="left",
                          origin="start_day").agg(
        {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
    ).dropna()
    return df[df["Volume"] > 0].copy()

def ensure_et(df):
    """Convert index to ET if not already."""
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(_ET)
    return df

# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

# ── V1: CLM 15m ───────────────────────────────────────────────────────────────
def build_v1():
    cfg = dict(ADX=18, PB=0.30, VOL=0.9, MIN_BODY=0.15, PANIC=1.5,
               RSI_LO_S=30, RSI_HI_S=60, SL=1.5, TP=2.0,
               TRAIL_ACT=3.5, TRAIL_DIST=1.2, ATR_FLOOR=0.001,
               SESSION_START=9, SESSION_END=12,
               DI_SPREAD=5.0, ADX_SLOPE=2, MOMENTUM=5,
               EMA_SLOPE_BARS=3)

    raw = load_intraday("15m"); raw.index = raw.index.tz_convert(_ET)
    df  = add_indicators(raw.copy())
    df  = ensure_et(df)

    tol       = cfg["PB"] / 100.0
    pb_dn     = df["EF"].shift(1) * (1.0 - tol)
    short_pb   = (df["High"].shift(1) >= pb_dn) & \
                 (df["Close"] < df["EF"]) & (df["Close"] < df["Open"])
    ema_bear   = (df["EF"] < df["EM"]) & (df["EM"] < df["ES"])
    ema_sl_dn  = df["EF"] < df["EF"].shift(cfg["EMA_SLOPE_BARS"])
    rsi_fall   = df["RSI"] < df["RSI"].shift(1)
    rsi_ok_s   = (df["RSI"] >= cfg["RSI_LO_S"]) & (df["RSI"] <= cfg["RSI_HI_S"])
    vol_ok     = df["Volume"] >= df["VOL_MA"] * cfg["VOL"]
    body_ok    = df["BODY"] >= cfg["MIN_BODY"]
    is_trend   = df["ADX"] > cfg["ADX"]
    not_panic  = df["ATR"] <= df["ATR_BL"] * cfg["PANIC"]
    atr_fl     = df["ATR"] / df["Close"] >= cfg["ATR_FLOOR"]
    adx_up     = df["ADX"] > df["ADX"].shift(cfg["ADX_SLOPE"])
    di_ok_s    = (df["DI-"] - df["DI+"]) >= cfg["DI_SPREAD"]
    mom_ok_s   = df["Close"] < df["Close"].shift(cfg["MOMENTUM"])
    session    = (df.index.hour >= cfg["SESSION_START"]) & \
                 (df.index.hour <  cfg["SESSION_END"])

    short_sig = (short_pb & ema_bear & ema_sl_dn & rsi_fall & rsi_ok_s &
                 vol_ok & body_ok & is_trend & not_panic & atr_fl &
                 adx_up & di_ok_s & mom_ok_s & session)
    long_sig  = pd.Series(False, index=df.index)

    df_ytd = df[df.index >= YTD_START].copy()
    ls_ytd = long_sig.reindex(df_ytd.index, fill_value=False)
    ss_ytd = short_sig.reindex(df_ytd.index, fill_value=False)

    sim_cfg = dict(sl=cfg["SL"], tp=cfg["TP"], trail_act=cfg["TRAIL_ACT"],
                   trail_dist=cfg["TRAIL_DIST"], max_bars=0,
                   consec_limit=2, consec_cool=1)
    return df_ytd, ls_ytd, ss_ytd, sim_cfg

# ── V2: CLM 30m ───────────────────────────────────────────────────────────────
def build_v2():
    cfg = dict(ADX=12, PB=0.30, VOL=0.5, MIN_BODY=0.15, PANIC=1.5,
               RSI_LO_S=30, RSI_HI_S=62, SL=2.0, TP=3.5,
               TRAIL_ACT=3.5, TRAIL_DIST=1.5,
               DI_SPREAD=3.0, ADX_SLOPE=1, MOMENTUM=5,
               EMA_SLOPE_BARS=3)

    raw = load_intraday("30m"); raw.index = raw.index.tz_convert(_ET)
    df  = add_indicators(raw.copy())
    df  = ensure_et(df)

    tol      = cfg["PB"] / 100.0
    pb_dn    = df["EF"].shift(1) * (1.0 - tol)
    short_pb  = (df["High"].shift(1) >= pb_dn) & \
                (df["Close"] < df["EF"]) & (df["Close"] < df["Open"])
    ema_bear  = (df["EF"] < df["EM"]) & (df["EM"] < df["ES"])
    ema_sl_dn = df["EF"] < df["EF"].shift(cfg["EMA_SLOPE_BARS"])
    rsi_fall  = df["RSI"] < df["RSI"].shift(1)
    rsi_ok_s  = (df["RSI"] >= cfg["RSI_LO_S"]) & (df["RSI"] <= cfg["RSI_HI_S"])
    vol_ok    = df["Volume"] >= df["VOL_MA"] * cfg["VOL"]
    body_ok   = df["BODY"] >= cfg["MIN_BODY"]
    is_trend  = df["ADX"] > cfg["ADX"]
    not_panic = df["ATR"] <= df["ATR_BL"] * cfg["PANIC"]
    adx_up    = df["ADX"] > df["ADX"].shift(cfg["ADX_SLOPE"])
    di_ok_s   = (df["DI-"] - df["DI+"]) >= cfg["DI_SPREAD"]
    mom_ok_s  = df["Close"] < df["Close"].shift(cfg["MOMENTUM"])

    short_sig = (short_pb & ema_bear & ema_sl_dn & rsi_fall & rsi_ok_s &
                 vol_ok & body_ok & is_trend & not_panic &
                 adx_up & di_ok_s & mom_ok_s)
    long_sig  = pd.Series(False, index=df.index)

    df_ytd = df[df.index >= YTD_START].copy()
    ls_ytd = long_sig.reindex(df_ytd.index, fill_value=False)
    ss_ytd = short_sig.reindex(df_ytd.index, fill_value=False)

    sim_cfg = dict(sl=cfg["SL"], tp=cfg["TP"], trail_act=cfg["TRAIL_ACT"],
                   trail_dist=cfg["TRAIL_DIST"], max_bars=0,
                   consec_limit=2, consec_cool=1)
    return df_ytd, ls_ytd, ss_ytd, sim_cfg

# ── V3: CLM 1h ────────────────────────────────────────────────────────────────
def build_v3():
    cfg = dict(ADX=33, PB=0.20, VOL=1.2, MIN_BODY=0.05, PANIC=1.4,
               RSI_LO_L=40, RSI_HI_L=70, RSI_LO_S=30, RSI_HI_S=60,
               SL=2.0, TP=2.0, TRAIL_ACT=99, TRAIL_DIST=0.3)

    raw = load_intraday("1h", period="max"); raw.index = raw.index.tz_convert(_ET)
    df  = add_indicators(raw.copy())
    df  = ensure_et(df)

    tol      = cfg["PB"] / 100.0
    pb_up    = df["EF"].shift(1) * (1.0 + tol)
    pb_dn    = df["EF"].shift(1) * (1.0 - tol)
    long_pb  = (df["Low"].shift(1) <= pb_up) & \
               (df["Close"] > df["EF"]) & (df["Close"] > df["Open"]) & \
               (df["BODY"] >= cfg["MIN_BODY"])
    short_pb = (df["High"].shift(1) >= pb_dn) & \
               (df["Close"] < df["EF"]) & (df["Close"] < df["Open"]) & \
               (df["BODY"] >= cfg["MIN_BODY"])
    is_trend  = df["ADX"] > cfg["ADX"]
    not_panic = df["ATR"] <= df["ATR_BL"] * cfg["PANIC"]

    long_sig = (
        long_pb &
        (df["Close"] > df["ES"]) & (df["EF"] > df["EM"]) &
        (df["RSI"] >= cfg["RSI_LO_L"]) & (df["RSI"] <= cfg["RSI_HI_L"]) &
        (df["Volume"] >= df["VOL_MA"] * cfg["VOL"]) &
        is_trend & not_panic
    )
    short_sig = (
        short_pb &
        (df["Close"] < df["ES"]) & (df["EF"] < df["EM"]) &
        (df["RSI"] >= cfg["RSI_LO_S"]) & (df["RSI"] <= cfg["RSI_HI_S"]) &
        (df["Volume"] >= df["VOL_MA"] * cfg["VOL"]) &
        is_trend & not_panic
    )

    df_ytd = df[df.index >= YTD_START].copy()
    ls_ytd = long_sig.reindex(df_ytd.index, fill_value=False)
    ss_ytd = short_sig.reindex(df_ytd.index, fill_value=False)

    sim_cfg = dict(sl=cfg["SL"], tp=cfg["TP"], trail_act=cfg["TRAIL_ACT"],
                   trail_dist=cfg["TRAIL_DIST"], max_bars=0,
                   consec_limit=2, consec_cool=1)
    return df_ytd, ls_ytd, ss_ytd, sim_cfg

# ── V4: CLM 1d ────────────────────────────────────────────────────────────────
def build_v4():
    cfg = dict(ADX=20, PB=0.30, VOL=1.0, MIN_BODY=0.20, PANIC=2.0,
               RSI_LO_L=42, RSI_HI_L=75,
               SL=1.5, TP=3.5, TRAIL_ACT=99, TRAIL_DIST=0.5, MAX_BARS=25,
               EMA_MID_SLOPE_LB=8)

    raw = load_intraday("1d", period="max"); raw.index = raw.index.tz_convert(_ET)
    df  = add_indicators(raw.copy())
    df  = ensure_et(df)

    tol      = cfg["PB"] / 100.0
    pb_up    = df["EF"].shift(1) * (1.0 + tol)
    long_pb  = (df["Low"].shift(1) <= pb_up) & \
               (df["Close"] > df["EF"]) & (df["Close"] > df["Open"]) & \
               (df["BODY"] >= cfg["MIN_BODY"])
    is_trend  = df["ADX"] > cfg["ADX"]
    not_panic = df["ATR"] <= df["ATR_BL"] * cfg["PANIC"]
    lb        = cfg["EMA_MID_SLOPE_LB"]
    em_slope  = df["EM"] > df["EM"].shift(lb) if lb > 0 else pd.Series(True, index=df.index)

    long_sig = (
        long_pb &
        (df["Close"] > df["ES"]) & (df["EF"] > df["EM"]) &
        (df["RSI"] >= cfg["RSI_LO_L"]) & (df["RSI"] <= cfg["RSI_HI_L"]) &
        (df["Volume"] >= df["VOL_MA"] * cfg["VOL"]) &
        is_trend & not_panic & em_slope
    )
    short_sig = pd.Series(False, index=df.index)

    df_ytd = df[df.index >= YTD_START].copy()
    ls_ytd = long_sig.reindex(df_ytd.index, fill_value=False)
    ss_ytd = short_sig.reindex(df_ytd.index, fill_value=False)

    sim_cfg = dict(sl=cfg["SL"], tp=cfg["TP"], trail_act=cfg["TRAIL_ACT"],
                   trail_dist=cfg["TRAIL_DIST"], max_bars=cfg["MAX_BARS"],
                   consec_limit=2, consec_cool=1)
    return df_ytd, ls_ytd, ss_ytd, sim_cfg

# ── V5: CLM 10m (Stage-3 params) ─────────────────────────────────────────────
def build_v5():
    cfg = dict(ADX=20, PB=0.30, VOL=0.7, MIN_BODY=0.15, PANIC=1.5,
               RSI_LO_S=32, RSI_HI_S=58,
               SL=2.0, TP=6.0, TRAIL_ACT=3.5, TRAIL_DIST=0.3,
               MAX_BARS=30, SESSION_START=9, SESSION_END=14,
               DI_SPREAD=0.0, MOMENTUM=5, ATR_FLOOR=0.0015)

    df  = load_10m()
    df  = add_indicators(df.copy())
    df  = ensure_et(df)

    tol      = cfg["PB"] / 100.0
    pb_dn    = df["EF"].shift(1) * (1.0 - tol)
    short_pb  = (df["High"].shift(1) >= pb_dn) & \
                (df["Close"] < df["EF"]) & (df["Close"] < df["Open"])
    ema_bear  = (df["EF"] < df["EM"]) & (df["EM"] < df["ES"])
    rsi_fall  = df["RSI"] < df["RSI"].shift(1)
    rsi_ok_s  = (df["RSI"] >= cfg["RSI_LO_S"]) & (df["RSI"] <= cfg["RSI_HI_S"])
    vol_ok    = df["Volume"] >= df["VOL_MA"] * cfg["VOL"]
    body_ok   = df["BODY"] >= cfg["MIN_BODY"]
    is_trend  = df["ADX"] > cfg["ADX"]
    not_panic = df["ATR"] <= df["ATR_BL"] * cfg["PANIC"]
    atr_fl    = df["ATR"] / df["Close"] >= cfg["ATR_FLOOR"]
    di_ok_s   = (df["DI-"] - df["DI+"]) >= cfg["DI_SPREAD"]
    mom_ok_s  = df["Close"] < df["Close"].shift(cfg["MOMENTUM"])
    session   = (df.index.hour >= cfg["SESSION_START"]) & \
                (df.index.hour <  cfg["SESSION_END"])

    short_sig = (short_pb & ema_bear & rsi_fall & rsi_ok_s &
                 vol_ok & body_ok & is_trend & not_panic & atr_fl &
                 di_ok_s & mom_ok_s & session)
    long_sig  = pd.Series(False, index=df.index)

    df_ytd = df[df.index >= YTD_START].copy()
    ls_ytd = long_sig.reindex(df_ytd.index, fill_value=False)
    ss_ytd = short_sig.reindex(df_ytd.index, fill_value=False)

    sim_cfg = dict(sl=cfg["SL"], tp=cfg["TP"], trail_act=cfg["TRAIL_ACT"],
                   trail_dist=cfg["TRAIL_DIST"], max_bars=cfg["MAX_BARS"],
                   consec_limit=2, consec_cool=1)
    return df_ytd, ls_ytd, ss_ytd, sim_cfg

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
strategies = [
    ("v1  CLM 15m (S)", "Shorts",     build_v1),
    ("v2  CLM 30m (S)", "Shorts",     build_v2),
    ("v3  CLM  1h (L+S)","Longs+Shorts", build_v3),
    ("v4  CLM  1d (L)", "Longs",      build_v4),
    ("v5  CLM 10m (S)", "Shorts",     build_v5),
]

results = []
for name, dirs, builder in strategies:
    print(f"Building {name} …", end=" ", flush=True)
    try:
        df_ytd, ls_ytd, ss_ytd, sim_cfg = builder()
        r = sim(df_ytd, ls_ytd, ss_ytd, sim_cfg)
        results.append((name, dirs, df_ytd, r))
        print(f"→ {r['trades']}T | WR={r['wr']}% | net={r['net_pct']:+.2f}%")
    except Exception as e:
        print(f"ERROR: {e}")
        results.append((name, dirs, None, None))

# ── Print comparison table ─────────────────────────────────────────────────────
print()
print("=" * 90)
print(f"  CLM APM v1–v5  ·  Year-To-Date Performance  ·  {YTD_START.date()} → 2026-03-11")
print("=" * 90)

hdr = (f"{'Strategy':<22} {'Dir':<12} {'TF':<5} {'Trades':>6} "
       f"{'WR':>6} {'PF':>8} {'Net%':>7} {'MaxDD':>7} {'Calmar':>8} "
       f"{'TP/SL/MB':>10}")
print(hdr)
print("-" * 90)

tf_map = {"v1":"15m","v2":"30m","v3":"1h","v4":"1d","v5":"10m"}
for name, dirs, df_ytd, r in results:
    if r is None:
        print(f"  {name:<20} {'ERR'}")
        continue
    key = name[:2]
    tf  = tf_map.get(key, "?")
    ytd_bars = f"({len(df_ytd)} bars)" if df_ytd is not None else ""
    pf_s     = f"{r['pf']:.3f}" if r["pf"] != float("inf") else "  inf"
    cal_s    = f"{r['calmar']:.2f}" if r["calmar"] != float("inf") else "   inf"
    exits    = f"{r['tp_exits']}/{r['sl_exits']}/{r['mb_exits']}"
    print(f"  {name:<20} {dirs:<12} {tf:<5} {r['trades']:>6} "
          f"  {r['wr']:>5.1f}% {pf_s:>8} {r['net_pct']:>+7.2f}% "
          f"{r['max_dd']:>7.2f}% {cal_s:>8} {exits:>10}")

print("-" * 90)
print("  TP/SL/MB = Take-Profit / Stop-Loss / Max-Bars exits")
print(f"  Capital: ${INITIAL_CAP:,.0f} per strategy  |  Risk: {RISK_PCT*100:.0f}%/trade  |  "
      f"Commission: {COMMISSION_PCT*100:.2f}%/side")
print()

# Best strategy summary
valids = [(n, r) for n, _, _, r in results if r and r["trades"] > 0]
if valids:
    best_net = max(valids, key=lambda x: x[1]["net_pct"])
    best_cal = max(valids, key=lambda x: x[1]["calmar"] if x[1]["calmar"] != float("inf") else x[1]["net_pct"])
    print(f"  Best net return : {best_net[0].strip()}  →  {best_net[1]['net_pct']:+.2f}%")
    print(f"  Best Calmar     : {best_cal[0].strip()}  →  {best_cal[1]['calmar']:.2f}")
print()
