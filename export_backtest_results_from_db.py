import sqlite3
import json
import os

# Path to the SQLite database
DB_PATH = 'docs/data/tradingcopilot.db'

# Output JSON files
BACKTEST_OUTPUT_PATH = 'docs/data/backtest_results.json'
PAPER_OUTPUT_PATH = 'docs/data/paper_trading_results.json'


conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Export backtest_results
c.execute('SELECT symbol, metrics FROM backtest_results')
backtest_result = {}
for symbol, metrics in c.fetchall():
    if symbol not in backtest_result:
        backtest_result[symbol] = []
    try:
        backtest_result[symbol].append(json.loads(metrics))
    except Exception:
        continue
with open(BACKTEST_OUTPUT_PATH, 'w') as f:
    json.dump(backtest_result, f, indent=2)
print(f'Exported backtest_results for all symbols to {BACKTEST_OUTPUT_PATH}')

# Export paper_trading_results
c.execute('SELECT symbol, metrics FROM paper_trading_results')
paper_result = {}
for symbol, metrics in c.fetchall():
    if symbol not in paper_result:
        paper_result[symbol] = []
    try:
        paper_result[symbol].append(json.loads(metrics))
    except Exception:
        continue
with open(PAPER_OUTPUT_PATH, 'w') as f:
    json.dump(paper_result, f, indent=2)
print(f'Exported paper_trading_results for all symbols to {PAPER_OUTPUT_PATH}')

conn.close()
