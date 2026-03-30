"""
Backtesting engine for Adaptive Pullback Momentum v1.0-5m (shorts only)
- Uses apm_v1_signals from apm_v1.py
- Simulates trade management: stop loss, take profit, trailing stop
"""
import pandas as pd
from apm_v1 import apm_v1_signals

# Trade management parameters (from Pine Script logic)
ATR_MULT_SL = 4.0   # Stop loss: entry + ATR * 4.0
ATR_MULT_TP = 8.0   # Take profit: entry - ATR * 8.0
ATR_MULT_TRAIL_ACT = 3.5  # Trail activates after price moves ATR*3.5 in favor
ATR_MULT_TRAIL_DIST = 0.1 # Trail distance from best price
RISK_PCT = 2.0      # 2% of equity risked per trade
INITIAL_EQUITY = 10000

# Main backtest function
def backtest_apm_v1(df):
    entries = apm_v1_signals(df)
    equity = INITIAL_EQUITY
    trades = []
    open_until = -1   # bar index at which the current trade exits
    for i in entries:
        if i <= open_until:   # skip signals while a trade is open
            continue
        entry_price = df['Close'].iloc[i]
        atr = df['atr'].iloc[i]
        sl = entry_price + ATR_MULT_SL * atr
        tp = entry_price - ATR_MULT_TP * atr
        trail_active = False
        best_price = entry_price
        qty = equity * RISK_PCT / 100 / (sl - entry_price) if (sl - entry_price) > 0 else 0
        exit_price = None
        exit_type = None
        for j in range(i+1, min(i+100, len(df))):  # Max 100 bars in trade
            price = df['Close'].iloc[j]
            if not trail_active and price < entry_price - ATR_MULT_TRAIL_ACT * atr:
                trail_active = True
                best_price = price
            if trail_active:
                best_price = min(best_price, price)
                trail_stop = best_price + ATR_MULT_TRAIL_DIST * atr
                if price > trail_stop:
                    exit_price = trail_stop
                    exit_type = 'trailing_stop'
                    break
            if price >= sl:
                exit_price = sl
                exit_type = 'stop_loss'
                break
            if price <= tp:
                exit_price = tp
                exit_type = 'take_profit'
                break
        if exit_price is None:
            j = min(i + 100, len(df) - 1)
            exit_price = df['Close'].iloc[j]
            exit_type = 'max_bars_exit'
        open_until = j
        pnl = (exit_price - entry_price) * qty * -1  # Short
        equity += pnl
        trades.append({'entry_idx': i, 'exit_idx': j, 'entry': entry_price, 'exit': exit_price, 'qty': qty, 'pnl': pnl, 'exit_type': exit_type, 'equity': equity})
    return pd.DataFrame(trades)

# Example usage (requires OHLCV DataFrame 'df' with indicators)
# trades = backtest_apm_v1(df)
# print(trades)
