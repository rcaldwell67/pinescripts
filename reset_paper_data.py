"""Force-reset paper trading data with corrected simulation."""
import sys
sys.path.insert(0, r'd:\OneDrive\codebase\pinescripts-1\backend')
sys.path.insert(0, r'd:\OneDrive\codebase\pinescripts-1\backend\strategy_generator')
import backend.paper_trading.paper_trade_backtrader_alpaca as pt

symbols = pt.load_symbols_from_db()
print(f"Running force-reset for: {symbols}")
for symbol in symbols:
    try:
        pt.run_one(symbol, 'v1', force_reset=True)
    except Exception as e:
        print(f"ERROR {symbol}: {e}")

import sqlite3
conn = sqlite3.connect(str(pt.DB_PATH))
rows = conn.execute("SELECT symbol, COUNT(*) FROM trades WHERE mode='paper' GROUP BY symbol").fetchall()
print("Verified rows:", rows)
conn.close()
