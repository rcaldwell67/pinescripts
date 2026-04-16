"""
Copy all symbols from alpaca_symbols to symbols table, skipping existing ones.
Optionally, add a default description and set live_enabled=0.
"""
import sqlite3
import os

def copy_alpaca_symbols_to_symbols():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend-react/public/data/tradingcopilot.db'))
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        # Ensure symbols table exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS symbols (
                symbol TEXT PRIMARY KEY,
                description TEXT,
                live_enabled INTEGER DEFAULT 0
            )
        ''')
        # Fetch all Alpaca symbols
        c.execute('SELECT symbol, name FROM alpaca_symbols')
        rows = c.fetchall()
        added = 0
        for symbol, name in rows:
            # Upsert: insert new, update existing
            c.execute('''
                INSERT INTO symbols (symbol, description, live_enabled)
                VALUES (?, ?, 0)
                ON CONFLICT(symbol) DO UPDATE SET
                  description=excluded.description,
                  live_enabled=excluded.live_enabled
            ''', (symbol, name))
            if c.rowcount:
                added += 1
        conn.commit()
        print(f"Added {added} new symbols from alpaca_symbols to symbols table.")
    finally:
        conn.close()

if __name__ == '__main__':
    copy_alpaca_symbols_to_symbols()
