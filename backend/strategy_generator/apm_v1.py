"""Adaptive Pullback Momentum v1.0-5m signal engine."""

import numpy as np
import pandas as pd

from v1_params import get_v1_params

# Helper functions for indicators
def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def rsi(series, length):
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(100.0)


def atr(df, length):
    prev_close = df['Close'].shift(1)
    tr = pd.concat(
        [
            (df['High'] - df['Low']).abs(),
            (df['High'] - prev_close).abs(),
            (df['Low'] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def dmi(df, length):
    high = df['High']
    low = df['Low']
    close = df['Close']

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_rma = tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean() / atr_rma
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean() / atr_rma
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    return plus_di, minus_di, adx, atr_rma

# Main strategy logic
def apm_v1_signals(df, params=None):
    params = params or get_v1_params()
    signal = params["signal"]

    ema_fast = int(signal["ema_fast"])
    ema_mid = int(signal["ema_mid"])
    ema_slow = int(signal["ema_slow"])
    slope_lookback = int(signal["ema_slope_lookback"])
    adx_threshold = float(signal.get("adx_threshold", 15))
    adx_slope_bars = int(signal.get("adx_slope_bars", 0))
    di_spread = float(signal.get("di_spread", 0.0))
    rsi_len = int(signal["rsi_len"])
    rsi_short_min = float(signal["rsi_short_min"])
    rsi_short_max = float(signal["rsi_short_max"])
    pb_tol_pct = float(signal["pullback_tolerance_pct"])
    momentum_bars = int(signal.get("momentum_bars", 5))
    volume_sma_len = int(signal["volume_sma_len"])
    volume_mult_min = float(signal["volume_mult_min"])
    min_body_atr_mult = float(signal["min_body_atr_mult"])
    atr_len = int(signal["atr_len"])
    atr_baseline_len = int(signal.get("atr_baseline_len", 60))
    atr_floor_pct = float(signal["atr_floor_pct"])
    panic_suppression_mult = float(signal.get("panic_suppression_mult", 1.5))
    session_filter_enabled = bool(signal.get("session_filter_enabled", True))
    session_start_hour_et = int(signal.get("session_start_hour_et", 9))
    session_end_hour_et = int(signal.get("session_end_hour_et", 14))
    macro_ema_period = int(signal.get("macro_ema_period", 0))

    # Calculate indicators
    df['ema21'] = ema(df['Close'], ema_fast)
    df['ema50'] = ema(df['Close'], ema_mid)
    df['ema200'] = ema(df['Close'], ema_slow)
    df['rsi'] = rsi(df['Close'], rsi_len)
    df['plus_di'], df['minus_di'], df['adx'], df['atr'] = dmi(df, atr_len)
    df['atr_baseline'] = df['atr'].rolling(atr_baseline_len).mean()
    df['vol_sma'] = df['Volume'].rolling(volume_sma_len).mean()
    if macro_ema_period > 0:
        df['macro_ema'] = ema(df['Close'], macro_ema_period)
    else:
        df['macro_ema'] = np.nan

    timestamps = pd.to_datetime(df.get('timestamp'), utc=True, errors='coerce')
    if timestamps is not None:
        try:
            et_hours = timestamps.dt.tz_convert('America/New_York').dt.hour
        except AttributeError:
            et_hours = pd.Series(np.nan, index=df.index)
    else:
        et_hours = pd.Series(np.nan, index=df.index)

    # Entry logic (shorts only)
    entries = []
    start_idx = max(ema_slow, slope_lookback + 1, momentum_bars, adx_slope_bars)
    for i in range(start_idx, len(df)):
        # Full bearish stack
        if not (df['ema21'].iloc[i] < df['ema50'].iloc[i] < df['ema200'].iloc[i]):
            continue
        # EMA21 falling over 3 bars
        if not (df['ema21'].iloc[i] < df['ema21'].iloc[i-slope_lookback]):
            continue
        # Trend strength
        if not pd.notna(df['adx'].iloc[i]) or df['adx'].iloc[i] <= adx_threshold:
            continue
        if adx_slope_bars > 0 and not (df['adx'].iloc[i] > df['adx'].iloc[i - adx_slope_bars]):
            continue
        # DI spread for bearish directional dominance
        if di_spread > 0 and not ((df['minus_di'].iloc[i] - df['plus_di'].iloc[i]) >= di_spread):
            continue
        # RSI falling on entry bar
        if not (df['rsi'].iloc[i] < df['rsi'].iloc[i-1]):
            continue
        # Multi-bar momentum confirms the down move
        if momentum_bars > 0 and not (df['Close'].iloc[i] < df['Close'].iloc[i - momentum_bars]):
            continue
        # Prev bar high tagged EMA21 zone, current bar breaks below EMA21
        pb_tol = df['ema21'].iloc[i-1] * (1 - (pb_tol_pct / 100.0))
        body = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
        if not (
            df['High'].iloc[i-1] >= pb_tol
            and df['Close'].iloc[i] < df['ema21'].iloc[i]
            and df['Close'].iloc[i] < df['Open'].iloc[i]
            and body >= min_body_atr_mult * df['atr'].iloc[i]
        ):
            continue
        # RSI 30–58
        if not (rsi_short_min <= df['rsi'].iloc[i] <= rsi_short_max):
            continue
        # Volume ≥ 0.3× VolSMA
        if not (df['Volume'].iloc[i] >= volume_mult_min * df['vol_sma'].iloc[i]):
            continue
        # ATR ≥ floor% of price
        if not (df['atr'].iloc[i] / df['Close'].iloc[i] * 100 >= atr_floor_pct):
            continue
        # Skip panic bars
        if pd.notna(df['atr_baseline'].iloc[i]) and df['atr'].iloc[i] > df['atr_baseline'].iloc[i] * panic_suppression_mult:
            continue
        # Session filter
        if session_filter_enabled:
            hour = et_hours.iloc[i]
            if not pd.notna(hour) or not (session_start_hour_et <= hour < session_end_hour_et):
                continue
        # Optional macro filter
        if macro_ema_period > 0 and not (df['Close'].iloc[i] < df['macro_ema'].iloc[i]):
            continue
        # If all conditions met, mark entry
        entries.append(i)
    return entries

# Example usage (requires OHLCV DataFrame 'df')
# entries = apm_v1_signals(df)
# print(entries)
