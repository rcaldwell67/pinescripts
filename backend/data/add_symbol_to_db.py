import sqlite3
import os
import sys

def add_symbol(symbol, description=None):
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db'))
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
                c.execute(
                        '''
                        INSERT INTO symbols (symbol, description)
                        VALUES (?, ?)
                        ON CONFLICT(symbol) DO UPDATE SET
                            description = COALESCE(excluded.description, symbols.description)
                        ''',
                        (symbol, description),
                )
        conn.commit()
        print(f"Symbol {symbol} added to database.")
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python add_symbol_to_db.py SYMBOL [DESCRIPTION]")
        sys.exit(1)
    symbol = sys.argv[1]
    description = sys.argv[2] if len(sys.argv) > 2 else None
    add_symbol(symbol, description)
