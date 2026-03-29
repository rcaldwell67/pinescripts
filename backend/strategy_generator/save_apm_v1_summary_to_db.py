import sqlite3
import os
import json
from summarize_apm_v1_results import (
    symbol, initial_equity, final_equity, total_trades, win_trades, loss_trades, win_rate, avg_pnl, total_pnl, max_drawdown, net_return_pct, first_trade_date, last_trade_date
)


def to_native(val):
    if hasattr(val, 'item'):
        return val.item()
    if hasattr(val, 'to_pydatetime'):
        return str(val)
    return val

def save_summary_to_db():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db'))
    metrics = {
        'beginning_equity': to_native(initial_equity),
        'final_equity': to_native(final_equity),
        'total_trades': to_native(total_trades),
        'winning_trades': to_native(win_trades),
        'losing_trades': to_native(loss_trades),
        'win_rate': to_native(win_rate),
        'average_pnl': to_native(avg_pnl),
        'total_pnl': to_native(total_pnl),
        'max_drawdown': to_native(max_drawdown),
        'net_return_pct': to_native(net_return_pct),
        'first_trade_date': str(first_trade_date),
        'last_trade_date': str(last_trade_date)
    }
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''INSERT INTO backtest_results (symbol, metrics, notes) VALUES (?, ?, ?)''',
              (symbol, json.dumps(metrics), 'APM v1.0-5m backtest summary'))
    conn.commit()
    conn.close()
    print(f"Summary saved to DB for symbol {symbol}")

if __name__ == '__main__':
    save_summary_to_db()
