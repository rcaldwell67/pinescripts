from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any

def compute_meanrev_tf_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute and add BB, EMA, RSI columns for mean reversion trend filter strategy.
    """
    bb_len = 20
    bb_std = 2.0
    ema_len = 200
    rsi_len = 15
    df = df.copy()
    df['bb_mid'] = df['Close'].rolling(bb_len).mean()
    bb_stddev = df['Close'].rolling(bb_len).std()
    df['bb_upper'] = df['bb_mid'] + bb_std * bb_stddev
    df['bb_lower'] = df['bb_mid'] - bb_std * bb_stddev
    df['ema200'] = df['Close'].ewm(span=ema_len, adjust=False).mean()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/rsi_len, min_periods=rsi_len, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/rsi_len, min_periods=rsi_len, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['rsi'] = (100 - (100 / (1 + rs))).fillna(100.0)
    return df

def mean_reversion_trendfilter_signals(df: pd.DataFrame, params: dict[str, Any] | None = None, use_precomputed: bool = False):
    """
    Entry: Long when Close < lower BB, RSI < 30, and Close > 200 EMA.
    Exits: TP 1.2% or close above BB mid, SL 0.8%, trailing stop after 0.5% profit (trail by 0.3%).
    """
    # --- Indicator calculations ---
    bb_len = 20
    entries = []
    for i in range(bb_len, len(df)):
        close = df['Close'].iloc[i]
        if (
            close < df['bb_lower'].iloc[i]
            and df['rsi'].iloc[i] < 30
            and close > df['ema200'].iloc[i]
        ):
            entries.append(i)
    return entries


def mean_reversion_trendfilter_exit(entry_price, current_price, bb_mid, tp_pct=0.012, sl_pct=0.008, trail_start=0.005, trail_pct=0.003):
    """
    Returns exit signal: 'tp', 'sl', 'trail', or None.
    """
    profit = (current_price - entry_price) / entry_price
    if profit >= tp_pct or current_price > bb_mid:
        return 'tp'
    if (entry_price - current_price) / entry_price >= sl_pct:
        return 'sl'
    if profit >= trail_start:
        trail_stop = entry_price * (1 + trail_start) * (1 - trail_pct)
        # Debug print for test
        # print(f"DEBUG: entry={entry_price}, current={current_price}, trail_stop={trail_stop}, profit={profit}")
        if current_price < trail_stop:
            return 'trail'
    return None


# Example usage (requires OHLCV DataFrame 'df' with columns: Open, High, Low, Close, Volume)
if __name__ == "__main__":
    import pandas as pd
    # Example: Load sample data (replace with your own CSV or DataFrame)
    # df = pd.read_csv("sample_ohlcv.csv")
    # For demonstration, create a dummy DataFrame
    n = 300
    df = pd.DataFrame({
        'Open': 100 + np.random.randn(n).cumsum(),
        'High': 100 + np.random.randn(n).cumsum() + 1,
        'Low': 100 + np.random.randn(n).cumsum() - 1,
        'Close': 100 + np.random.randn(n).cumsum(),
        'Volume': np.random.randint(100, 1000, n),
    })
    entries = mean_reversion_trendfilter_signals(df)
    print(f"Entry indices: {entries}")
    # Simulate a trade exit for the first entry (if any)
    if entries:
        i = entries[0]
        entry_price = df['Close'].iloc[i]
        bb_mid = df['bb_mid'].iloc[i]
        # Simulate price movement
        for j in range(i+1, min(i+20, len(df))):
            current_price = df['Close'].iloc[j]
            exit_signal = mean_reversion_trendfilter_exit(entry_price, current_price, bb_mid)
            if exit_signal:
                print(f"Exit at idx {j}: {exit_signal}, price={current_price}")
                break
