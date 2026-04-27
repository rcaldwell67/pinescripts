"""
Unit test for mean_reversion_trendfilter_v1.py
"""
import pandas as pd
import numpy as np
from mean_reversion_trendfilter_v1 import mean_reversion_trendfilter_signals, mean_reversion_trendfilter_exit

def test_entry_logic():
    n = 100
    df = pd.DataFrame({
        'Open': np.linspace(100, 90, n),
        'High': np.linspace(101, 91, n),
        'Low': np.linspace(99, 89, n),
        'Close': np.linspace(100, 85, n),
        'Volume': np.random.randint(100, 1000, n),
    })
    idx = 30
    # Patch indicators to guarantee entry at idx
    from mean_reversion_trendfilter_v1 import mean_reversion_trendfilter_signals, compute_meanrev_tf_indicators
    # Compute indicators
    df = compute_meanrev_tf_indicators(df)
    # Patch a range of indices to guarantee entry
    for idx in range(30, 35):
        df.loc[idx, 'bb_lower'] = df['Close'].iloc[idx] + 1
        df.loc[idx, 'rsi'] = 20
        df.loc[idx, 'ema200'] = df['Close'].iloc[idx] - 1
        df.loc[idx, 'Close'] = df['bb_lower'].iloc[idx] - 1
    entries = mean_reversion_trendfilter_signals(df, use_precomputed=True)
    assert isinstance(entries, list)
    found = any(idx in entries for idx in range(30, 35))
    assert found

def test_exit_logic():
    entry_price = 100
    bb_mid = 101
    # TP
    assert mean_reversion_trendfilter_exit(entry_price, 101.5, bb_mid) == 'tp'
    # SL
    assert mean_reversion_trendfilter_exit(entry_price, 99.1, bb_mid) == 'sl'
    # Trailing (should not trigger yet)
    assert mean_reversion_trendfilter_exit(entry_price, 100.6, bb_mid) is None  # Not enough profit
    # After 0.5% profit, price drops by 0.3% (simulate trailing stop logic)
    trail_start = 0
    trail_pct = 0.05
    max_profit_price = entry_price * (1 + 0.10)  # Simulate a 10% run-up
    trail_stop = max_profit_price * (1 - trail_pct)
    # Set current_price just below trail_stop, but above entry
    current_price = trail_stop - 0.01
    profit = (current_price - entry_price) / entry_price
    print(f"entry_price={entry_price}, trail_stop={trail_stop}, current_price={current_price}, profit={profit}")
    assert current_price < trail_stop
    assert current_price > entry_price
    assert mean_reversion_trendfilter_exit(entry_price, current_price, bb_mid, trail_start=trail_start, trail_pct=trail_pct) == 'tp'

if __name__ == "__main__":
    test_entry_logic()
    test_exit_logic()
    print("All tests passed.")
