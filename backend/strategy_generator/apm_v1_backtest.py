"""
Backtesting engine for Adaptive Pullback Momentum v1.0-5m (shorts only)
- Uses apm_v1_signals from apm_v1.py
- Simulates trade management: stop loss, take profit, trailing stop
"""
import pandas as pd
from apm_v1 import apm_v1_signals
from v1_params import get_v1_params

# Main backtest function
def backtest_apm_v1(df, params=None):
    params = params or get_v1_params()
    risk = params["risk"]
    entries = apm_v1_signals(df, params=params)
    equity = float(risk["initial_equity"])
    trades = []
    open_until = -1   # bar index at which the current trade exits
    sl_mult = float(risk["sl_atr_mult"])
    tp_mult = float(risk["tp_atr_mult"])
    trail_activate_mult = float(risk["trail_activate_atr_mult"])
    trail_dist_mult = float(risk["trail_dist_atr_mult"])
    risk_pct = float(risk["risk_pct"])
    max_bars = int(risk["max_bars_in_trade"])

    for i in entries:
        if i <= open_until:   # skip signals while a trade is open
            continue
        entry_price = df['Close'].iloc[i]
        atr = df['atr'].iloc[i]
        sl = entry_price + sl_mult * atr
        tp = entry_price - tp_mult * atr
        trail_active = False
        best_price = entry_price
        qty = equity * risk_pct / 100 / (sl - entry_price) if (sl - entry_price) > 0 else 0
        exit_price = None
        exit_type = None
        for j in range(i+1, min(i + max_bars, len(df))):
            price = df['Close'].iloc[j]
            if not trail_active and price < entry_price - trail_activate_mult * atr:
                trail_active = True
                best_price = price
            if trail_active:
                best_price = min(best_price, price)
                trail_stop = best_price + trail_dist_mult * atr
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
            j = min(i + max_bars, len(df) - 1)
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
