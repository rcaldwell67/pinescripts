"""
Adaptive Pullback Momentum v1.0-5m (Python version)
Replicates the Pine Script logic for backtesting/analysis.
"""
import pandas as pd
import numpy as np
from v1_params import get_v1_params

# Helper functions for indicators
def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def rsi(series, length):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(length).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(length).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def atr(df, length):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(length).mean()

# Placeholder for ADX (to be implemented)
def adx(df, length):
    # TODO: Implement full ADX calculation
    return pd.Series(np.nan, index=df.index)

# Main strategy logic
def apm_v1_signals(df, params=None):
    params = params or get_v1_params()
    signal = params["signal"]

    ema_fast = int(signal["ema_fast"])
    ema_mid = int(signal["ema_mid"])
    ema_slow = int(signal["ema_slow"])
    slope_lookback = int(signal["ema_slope_lookback"])
    rsi_len = int(signal["rsi_len"])
    rsi_short_min = float(signal["rsi_short_min"])
    rsi_short_max = float(signal["rsi_short_max"])
    pb_tol_pct = float(signal["pullback_tolerance_pct"])
    volume_sma_len = int(signal["volume_sma_len"])
    volume_mult_min = float(signal["volume_mult_min"])
    min_body_atr_mult = float(signal["min_body_atr_mult"])
    atr_len = int(signal["atr_len"])
    atr_floor_pct = float(signal["atr_floor_pct"])

    # Calculate indicators
    df['ema21'] = ema(df['Close'], ema_fast)
    df['ema50'] = ema(df['Close'], ema_mid)
    df['ema200'] = ema(df['Close'], ema_slow)
    df['rsi'] = rsi(df['Close'], rsi_len)
    df['atr'] = atr(df, atr_len)
    df['vol_sma'] = df['Volume'].rolling(volume_sma_len).mean()
    # TODO: Add ADX, DI+ and DI- calculations

    # Entry logic (shorts only)
    entries = []
    start_idx = max(ema_slow, slope_lookback + 1)
    for i in range(start_idx, len(df)):
        # Full bearish stack
        if not (df['ema21'].iloc[i] < df['ema50'].iloc[i] < df['ema200'].iloc[i]):
            continue
        # EMA21 falling over 3 bars
        if not (df['ema21'].iloc[i] < df['ema21'].iloc[i-slope_lookback]):
            continue
        # RSI falling on entry bar
        if not (df['rsi'].iloc[i] < df['rsi'].iloc[i-1]):
            continue
        # Prev bar high tagged EMA21 zone, current bar breaks below EMA21
        pb_tol = df['ema21'].iloc[i-1] * (1 - (pb_tol_pct / 100.0))
        if not (df['High'].iloc[i-1] >= pb_tol and df['Close'].iloc[i] < df['ema21'].iloc[i]):
            continue
        # RSI 30–58
        if not (rsi_short_min <= df['rsi'].iloc[i] <= rsi_short_max):
            continue
        # Volume ≥ 0.3× VolSMA
        if not (df['Volume'].iloc[i] >= volume_mult_min * df['vol_sma'].iloc[i]):
            continue
        # Body ≥ 0.15×ATR
        body = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
        if not (body >= min_body_atr_mult * df['atr'].iloc[i]):
            continue
        # ATR ≥ floor% of price
        if not (df['atr'].iloc[i] >= (atr_floor_pct / 100.0) * df['Close'].iloc[i]):
            continue
        # If all conditions met, mark entry
        entries.append(i)
    return entries

# Example usage (requires OHLCV DataFrame 'df')
# entries = apm_v1_signals(df)
# print(entries)
