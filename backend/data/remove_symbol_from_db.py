"""Remove a symbol from the symbols table in tradingcopilot.db."""

import sys
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

def main():
    if len(sys.argv) < 2:
        print("Usage: python remove_symbol_from_db.py <SYMBOL>")
        sys.exit(1)

    symbol = sys.argv[1].upper().strip()


    def get_db_conn():
        return mysql.connector.connect(
            host=os.environ.get("MARIADB_HOST", "localhost"),
            user=os.environ.get("MARIADB_USER", "root"),
            password=os.environ.get("MARIADB_PASSWORD", ""),
            database=os.environ.get("MARIADB_DATABASE", "tradingcopilot"),
            port=int(os.environ.get("MARIADB_PORT", 3306)),
        )

    conn = get_db_conn()
    c = conn.cursor()

    c.execute('SELECT symbol FROM symbols WHERE symbol = %s', (symbol,))
    row = c.fetchone()
    if not row:
        print(f"Symbol {symbol} not found in database.")
        conn.close()
        sys.exit(1)

    c.execute('DELETE FROM symbols WHERE symbol = %s', (symbol,))
    conn.commit()
    conn.close()
    print(f"Symbol {symbol} removed from database.")
    # No need to copy DB, canonical location is already used

if __name__ == '__main__':
    main()
