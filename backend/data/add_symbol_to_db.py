
import mysql.connector
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))



def get_db_conn():
    return mysql.connector.connect(
        host=os.environ.get("MARIADB_HOST", "localhost"),
        user=os.environ.get("MARIADB_USER", "root"),
        password=os.environ.get("MARIADB_PASSWORD", ""),
        database=os.environ.get("MARIADB_DATABASE", "tradingcopilot"),
        port=int(os.environ.get("MARIADB_PORT", 3306)),
    )

def add_symbol(symbol, description=None, isactive=1, asset_type=None):
    conn = get_db_conn()
    c = conn.cursor()
    try:
        # MariaDB uses %s for parameter placeholders
        c.execute(
            '''
            INSERT INTO symbols (symbol, description, isactive, asset_type, live_enabled)
            VALUES (%s, %s, %s, %s, 0)
            ON DUPLICATE KEY UPDATE
              description = COALESCE(VALUES(description), description),
              isactive = VALUES(isactive),
              asset_type = COALESCE(VALUES(asset_type), asset_type),
              live_enabled = live_enabled
            ''',
            (symbol, description, isactive, asset_type),
        )
        conn.commit()
        print(f"Symbol {symbol} added to database as ACTIVE (isactive=1, live_enabled=0). Vet before enabling.")
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python add_symbol_to_db.py SYMBOL [DESCRIPTION] [ASSET_TYPE] [ISACTIVE]")
        sys.exit(1)
    symbol = sys.argv[1]
    description = sys.argv[2] if len(sys.argv) > 2 else None
    asset_type = sys.argv[3] if len(sys.argv) > 3 else None
    isactive = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    add_symbol(symbol, description, isactive, asset_type)
