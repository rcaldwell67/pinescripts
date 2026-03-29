"""
Adaptive Pullback Momentum v1.0-5m (Python version)
Replicates the Pine Script logic for backtesting/analysis.
"""
import pandas as pd
import numpy as np

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
def apm_v1_signals(df):
    # Calculate indicators
    df['ema21'] = ema(df['Close'], 21)
    df['ema50'] = ema(df['Close'], 50)
    df['ema200'] = ema(df['Close'], 200)
    df['rsi'] = rsi(df['Close'], 14)
    df['atr'] = atr(df, 14)
    df['vol_sma'] = df['Volume'].rolling(20).mean()
    # TODO: Add ADX, DI+ and DI- calculations

    # Entry logic (shorts only)
    entries = []
    for i in range(200, len(df)):
        # Full bearish stack
        if not (df['ema21'].iloc[i] < df['ema50'].iloc[i] < df['ema200'].iloc[i]):
            continue
        # EMA21 falling over 3 bars
        if not (df['ema21'].iloc[i] < df['ema21'].iloc[i-3]):
            continue
        # RSI falling on entry bar
        if not (df['rsi'].iloc[i] < df['rsi'].iloc[i-1]):
            continue
        # Prev bar high tagged EMA21 zone, current bar breaks below EMA21
        pb_tol = df['ema21'].iloc[i-1] * (1 - 0.004)  # 0.4% pullback tolerance
        if not (df['High'].iloc[i-1] >= pb_tol and df['Close'].iloc[i] < df['ema21'].iloc[i]):
            continue
        # RSI 30–58
        if not (30 <= df['rsi'].iloc[i] <= 58):
            continue
        # Volume ≥ 0.3× VolSMA
        if not (df['Volume'].iloc[i] >= 0.3 * df['vol_sma'].iloc[i]):
            continue
        # Body ≥ 0.15×ATR
        body = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
        if not (body >= 0.15 * df['atr'].iloc[i]):
            continue
        # ATR ≥ 0.1% of price
        if not (df['atr'].iloc[i] >= 0.001 * df['Close'].iloc[i]):
            continue
        # If all conditions met, mark entry
        entries.append(i)
    return entries

# Example usage (requires OHLCV DataFrame 'df')
# entries = apm_v1_signals(df)
# print(entries)
