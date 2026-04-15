"""
Update asset_type for all active symbols in the symbols table using the type from alpaca_symbols.
Run: python update_symbol_asset_types.py
"""
import sqlite3
import os

def update_symbol_asset_types():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db'))
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        # Get all symbol/type pairs from alpaca_symbols
        c.execute('SELECT symbol, type FROM alpaca_symbols')
        rows = c.fetchall()
        updated = 0
        for symbol, asset_type in rows:
            # Update asset_type in symbols table if symbol exists
            c.execute('UPDATE symbols SET asset_type = ? WHERE symbol = ?', (asset_type, symbol))
            if c.rowcount > 0:
                updated += 1
        conn.commit()
        print(f"Updated asset_type for {updated} symbols in the symbols table.")
    finally:
        conn.close()

if __name__ == '__main__':
    update_symbol_asset_types()
