import pandas as pd


trades = pd.read_csv('apm_v1_trades.csv')

# Load original OHLCV data to get timestamps
import os
import pandas as pd
ohlcv_path = os.path.join(os.path.dirname(__file__), '../data/btc_usd_5m_ytd.csv')
ohlcv = pd.read_csv(os.path.abspath(ohlcv_path), parse_dates=['timestamp'])
# Extract symbol from filename
import re
symbol_match = re.search(r'([a-zA-Z0-9]+_[a-zA-Z0-9]+)', os.path.basename(ohlcv_path))
symbol = symbol_match.group(1).upper() if symbol_match else 'UNKNOWN'

# Basic metrics
total_trades = len(trades)
win_trades = (trades['pnl'] > 0).sum()
loss_trades = (trades['pnl'] <= 0).sum()
win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
avg_pnl = trades['pnl'].mean()
total_pnl = trades['pnl'].sum()
max_drawdown = (trades['equity'].cummax() - trades['equity']).max()

final_equity = trades['equity'].iloc[-1] if total_trades > 0 else 0
initial_equity = trades['equity'].iloc[0] if total_trades > 0 else 0
net_return_pct = ((final_equity - initial_equity) / initial_equity * 100) if initial_equity > 0 else 0

# Get first and last trade dates
first_trade_date = None
last_trade_date = None
if total_trades > 0:
	first_idx = int(trades['entry_idx'].iloc[0])
	last_idx = int(trades['entry_idx'].iloc[-1])
	first_trade_date = ohlcv['timestamp'].iloc[first_idx]
	last_trade_date = ohlcv['timestamp'].iloc[last_idx]

# Print summary
print(f"APM v1.0-5m Backtest Summary\n{'='*30}")
print(f"Symbol: {symbol}")
print(f"Beginning equity: {initial_equity:.2f}")
print(f"Total trades: {total_trades}")
if first_trade_date is not None and last_trade_date is not None:
	print(f"First trade date: {first_trade_date}")
	print(f"Last trade date: {last_trade_date}")
print(f"Winning trades: {win_trades}")
print(f"Losing trades: {loss_trades}")
print(f"Win rate: {win_rate:.2f}%")
print(f"Average PnL per trade: {avg_pnl:.2f}")
print(f"Total PnL: {total_pnl:.2f}")
print(f"Max drawdown: {max_drawdown:.2f}")
print(f"Final equity: {final_equity:.2f}")
print(f"Net return: {net_return_pct:.2f}%")
