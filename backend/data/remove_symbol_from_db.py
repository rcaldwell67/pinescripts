"""Remove a symbol from the symbols table in tradingcopilot.db."""
import sys
import os
import sqlite3

def main():
    if len(sys.argv) < 2:
        print("Usage: python remove_symbol_from_db.py <SYMBOL>")
        sys.exit(1)

    symbol = sys.argv[1].upper().strip()

    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend-react/public/data/tradingcopilot.db'))
    if not os.path.exists(db_path):
        print(f"Error: tradingcopilot.db not found at {db_path}.")
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
    # No need to copy DB, canonical location is already used

if __name__ == '__main__':
    main()
