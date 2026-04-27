"""
Backtest runner for Mean Reversion Trend Filter strategy (long only)
- Uses mean_reversion_trendfilter_signals from mean_reversion_trendfilter_v1.py
- Simulates trade management: stop loss, take profit, trailing stop
"""
import pandas as pd
from mean_reversion_trendfilter_v1 import mean_reversion_trendfilter_signals, mean_reversion_trendfilter_exit

def backtest_mean_reversion_trendfilter(df, params=None):
    entries = mean_reversion_trendfilter_signals(df, params=params)
    equity = 100000.0
    trades = []
    open_until = -1
    for i in entries:
        if i <= open_until:
            continue
        entry_price = df['Close'].iloc[i]
        bb_mid = df['bb_mid'].iloc[i]
        qty = equity * 0.01 / entry_price  # 1% risk per trade (example)
        exit_price = None
        exit_type = None
        for j in range(i+1, min(i+100, len(df))):
            current_price = df['Close'].iloc[j]
            signal = mean_reversion_trendfilter_exit(entry_price, current_price, bb_mid)
            if signal:
                exit_price = current_price
                exit_type = signal
                break
        if exit_price is None:
            j = min(i+100, len(df)-1)
            exit_price = df['Close'].iloc[j]
            exit_type = 'max_bars_exit'
        open_until = j
        pnl = (exit_price - entry_price) * qty
        equity += pnl
        trades.append({'entry_idx': i, 'exit_idx': j, 'entry': entry_price, 'exit': exit_price, 'qty': qty, 'pnl': pnl, 'exit_type': exit_type, 'equity': equity})
    return pd.DataFrame(trades)

# Example usage (requires OHLCV DataFrame 'df')
# trades = backtest_mean_reversion_trendfilter(df)
# print(trades)
