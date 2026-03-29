import sqlite3
import json
import os

# Path to the SQLite database
DB_PATH = 'docs/data/tradingcopilot.db'
# Output JSON file
OUTPUT_PATH = 'docs/data/backtest_results.json'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('SELECT symbol, metrics FROM backtest_results')
result = {}
for symbol, metrics in c.fetchall():
    if symbol not in result:
        result[symbol] = []
    try:
        result[symbol].append(json.loads(metrics))
    except Exception:
        continue
with open(OUTPUT_PATH, 'w') as f:
    json.dump(result, f, indent=2)
conn.close()
print(f'Exported backtest_results for all symbols to {OUTPUT_PATH}')
