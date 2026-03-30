"""Force-reset paper trading data in temp DB, then commit the file."""
import sys
from pathlib import Path
sys.path.insert(0, r'd:\OneDrive\codebase\pinescripts-1\backend')
sys.path.insert(0, r'd:\OneDrive\codebase\pinescripts-1\backend\strategy_generator')
import backend.paper_trading.paper_trade_backtrader_alpaca as pt

# Point to temp DB
tmp = Path(r'd:\OneDrive\codebase\pinescripts-1\docs\data\tradingcopilot.reset.tmp.db')
pt.DB_PATH = tmp

symbols = pt.load_symbols_from_db()
print(f"Symbols: {symbols}")
for symbol in symbols:
    try:
        pt.run_one(symbol, 'v1', force_reset=True)
    except Exception as e:
        print(f"ERROR {symbol}: {e}")

import sqlite3
conn = sqlite3.connect(str(tmp))
rows = conn.execute("SELECT symbol, COUNT(*) FROM trades WHERE mode='paper' GROUP BY symbol").fetchall()
print("Paper trade rows:", rows)
rows2 = conn.execute("SELECT symbol, metrics FROM paper_trading_results").fetchall()
import json
for sym, m in rows2:
    d = json.loads(m)
    print(f"  {sym}: {d['total_trades']} trades, net_ret={d['net_return_pct']:.1f}%")
conn.close()
