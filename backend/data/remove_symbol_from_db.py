"""Remove a symbol from the symbols table in tradingcopilot.db."""
import sys
import os
import sqlite3

def main():
    if len(sys.argv) < 2:
        print("Usage: python remove_symbol_from_db.py <SYMBOL>")
        sys.exit(1)

    symbol = sys.argv[1].upper().strip()

    db_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'data', 'tradingcopilot.db'),
        'docs/data/tradingcopilot.db',
    ]

    db_path = None
    for p in db_paths:
        if os.path.exists(p):
            db_path = p
            break

    if not db_path:
        print(f"Error: tradingcopilot.db not found in expected locations.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute('SELECT symbol FROM symbols WHERE symbol = ?', (symbol,))
    row = c.fetchone()
    if not row:
        print(f"Symbol {symbol} not found in database.")
        conn.close()
        sys.exit(1)

    c.execute('DELETE FROM symbols WHERE symbol = ?', (symbol,))
    conn.commit()
    conn.close()
    print(f"Symbol {symbol} removed from database.")
    # Copy to frontend-react/public/data
    import shutil
    public_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend-react/public/data/tradingcopilot.db'))
    try:
        shutil.copyfile(db_path, public_db_path)
        print(f"Copied DB to {public_db_path}")
    except Exception as e:
        print(f"Warning: Failed to copy DB to frontend-react/public/data: {e}")

if __name__ == '__main__':
    main()
