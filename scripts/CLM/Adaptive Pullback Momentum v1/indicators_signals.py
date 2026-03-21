# indicators_signals.py
"""
Shared indicator and signal logic for APM v1.0 CLM 5m backtest and sweep scripts.
Ensures both scripts use identical calculations and signal definitions.
"""
import pandas as pd
import numpy as np

def build_indicators_signals(
    df,
    ema_fast=21, ema_mid=50, ema_slow=200,
    adx_len=14, rsi_len=14, atr_len=14, vol_len=20, atr_bl_len=60,
    adx_thresh=20, pb_pct=0.20, vol_mult=0.7, atr_floor=0.0015, panic_mult=1.5,
    ema_slope_bars=3, momentum_bars=5, min_body=0.15,
    di_spread_min=0.0, adx_slope_bars=0,
    rsi_lo_s=30, rsi_hi_s=58, rsi_lo_l=42, rsi_hi_l=68,
    session_start=9, session_end=14,
    trade_longs=False, trade_shorts=True
):
    d = df.copy()
    d["EMA_FAST"] = d["Close"].ewm(span=ema_fast, adjust=False).mean()
    d["EMA_MID"]  = d["Close"].ewm(span=ema_mid,  adjust=False).mean()
    d["EMA_SLOW"] = d["Close"].ewm(span=ema_slow, adjust=False).mean()

    delta = d["Close"].diff()
    avg_g = delta.clip(lower=0).ewm(alpha=1/rsi_len, adjust=False).mean()
    avg_l = (-delta).clip(lower=0).ewm(alpha=1/rsi_len, adjust=False).mean()
    d["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

    hl  = d["High"] - d["Low"]
    hpc = (d["High"] - d["Close"].shift(1)).abs()
    lpc = (d["Low"]  - d["Close"].shift(1)).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    d["ATR"]    = tr.ewm(alpha=1/atr_len, adjust=False).mean()
    d["ATR_BL"] = d["ATR"].rolling(atr_bl_len).mean()
    d["VOL_MA"] = d["Volume"].rolling(vol_len).mean()

    up_move  = d["High"] - d["High"].shift(1)
    dn_move  = d["Low"].shift(1) - d["Low"]
    plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
    s_plus   = pd.Series(plus_dm,  index=d.index).ewm(alpha=1/adx_len, adjust=False).mean()
    s_minus  = pd.Series(minus_dm, index=d.index).ewm(alpha=1/adx_len, adjust=False).mean()
    d["DI_PLUS"]  = 100 * s_plus  / d["ATR"].replace(0, 1e-10)
    d["DI_MINUS"] = 100 * s_minus / d["ATR"].replace(0, 1e-10)
    dx = 100 * (d["DI_PLUS"] - d["DI_MINUS"]).abs() / (
         (d["DI_PLUS"] + d["DI_MINUS"]).replace(0, 1e-10))
    d["ADX"] = dx.ewm(alpha=1/adx_len, adjust=False).mean()

    d.dropna(inplace=True)
    d["ET_HOUR"] = d.index.hour

    tol = pb_pct / 100.0
    pb_tol_up = d["EMA_FAST"].shift(1) * (1.0 + tol)
    pb_tol_dn = d["EMA_FAST"].shift(1) * (1.0 - tol)
    long_pb   = (d["Low"].shift(1)  <= pb_tol_up) & (d["Close"] > d["EMA_FAST"]) & (d["Close"] > d["Open"])
    short_pb  = (d["High"].shift(1) >= pb_tol_dn) & (d["Close"] < d["EMA_FAST"]) & (d["Close"] < d["Open"])

    body_ok    = (d["Close"] - d["Open"]).abs() / d["ATR"].replace(0, 1e-10) >= min_body
    vol_ok     = d["Volume"] >= d["VOL_MA"] * vol_mult
    rsi_rising  = d["RSI"] > d["RSI"].shift(1)
    rsi_falling = d["RSI"] < d["RSI"].shift(1)
    rsi_long_ok  = (d["RSI"] >= rsi_lo_l) & (d["RSI"] <= rsi_hi_l)
    rsi_short_ok = (d["RSI"] >= rsi_lo_s) & (d["RSI"] <= rsi_hi_s)

    di_spread_ok_s = ((d["DI_MINUS"] - d["DI_PLUS"]) >= di_spread_min)
    di_spread_ok_l = ((d["DI_PLUS"]  - d["DI_MINUS"]) >= di_spread_min)

    adx_rising = (pd.Series(True, index=d.index) if adx_slope_bars == 0
                  else d["ADX"] > d["ADX"].shift(adx_slope_bars))

    mom_ok_s = d["Close"] < d["Close"].shift(momentum_bars)
    mom_ok_l = d["Close"] > d["Close"].shift(momentum_bars)

    is_trending = d["ADX"] > adx_thresh
    is_panic    = d["ATR"] > d["ATR_BL"] * panic_mult
    atr_fl      = d["ATR"] / d["Close"] >= atr_floor

    ema_bull = (d["EMA_FAST"] > d["EMA_MID"]) & (d["EMA_MID"] > d["EMA_SLOW"])
    ema_bear = (d["EMA_FAST"] < d["EMA_MID"]) & (d["EMA_MID"] < d["EMA_SLOW"])

    ema_slope_up   = (pd.Series(True, index=d.index) if ema_slope_bars == 0
                      else d["EMA_FAST"] > d["EMA_FAST"].shift(ema_slope_bars))
    ema_slope_down = (pd.Series(True, index=d.index) if ema_slope_bars == 0
                      else d["EMA_FAST"] < d["EMA_FAST"].shift(ema_slope_bars))

    session_ok = (d["ET_HOUR"] >= session_start) & (d["ET_HOUR"] < session_end)

    short_signal = (
        trade_shorts & short_pb & ema_bear & ema_slope_down & rsi_falling & rsi_short_ok &
        vol_ok & body_ok & is_trending & adx_rising & di_spread_ok_s & mom_ok_s & session_ok & ~is_panic & atr_fl
    )
    long_signal = (
        trade_longs & long_pb & ema_bull & ema_slope_up & rsi_rising & rsi_long_ok &
        vol_ok & body_ok & is_trending & adx_rising & di_spread_ok_l & mom_ok_l & session_ok & ~is_panic & atr_fl
    )
    return d, long_signal, short_signal
