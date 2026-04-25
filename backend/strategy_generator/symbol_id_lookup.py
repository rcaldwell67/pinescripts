import mysql.connector
import os
from dotenv import load_dotenv

def get_symbol_id(symbol: str) -> int:
    """Fetch the id for the given symbol from the MariaDB symbols table."""
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))
    conn = mysql.connector.connect(
        host=os.environ.get("MARIADB_HOST", "localhost"),
        user=os.environ.get("MARIADB_USER", "root"),
        password=os.environ.get("MARIADB_PASSWORD", ""),
        database=os.environ.get("MARIADB_DATABASE", "tradingcopilot"),
        port=int(os.environ.get("MARIADB_PORT", 3306)),
    )
    c = conn.cursor()
    c.execute('SELECT id FROM symbols WHERE symbol = %s AND isactive=1', (symbol,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return None
