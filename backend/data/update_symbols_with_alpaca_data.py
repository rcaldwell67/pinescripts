

import requests
import os
import mysql.connector
import json
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("update_symbols_with_alpaca_data")

ALPACA_API_KEY = os.getenv('ALPACA_PAPER_API_KEY') or os.getenv('ALPACA_API_KEY')
ALPACA_API_SECRET = os.getenv('ALPACA_PAPER_API_SECRET') or os.getenv('ALPACA_API_SECRET')
HEADERS = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_API_SECRET
}

ALPACA_ASSETS_URL = 'https://paper-api.alpaca.markets/v2/assets'

def get_db_conn():
    return mysql.connector.connect(
        host=os.environ.get("MARIADB_HOST", "localhost"),
        user=os.environ.get("MARIADB_USER", "root"),
        password=os.environ.get("MARIADB_PASSWORD", ""),
        database=os.environ.get("MARIADB_DATABASE", "tradingcopilot"),
        port=int(os.environ.get("MARIADB_PORT", 3306)),
    )

def update_symbols_table_with_alpaca_data():
    try:
        resp = requests.get(ALPACA_ASSETS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        assets = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch Alpaca assets: {e}")
        return 1

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        for asset in assets:
            symbol = asset['symbol']
            # Check if symbol exists
            cur.execute('SELECT COUNT(*) FROM symbols WHERE symbol = %s', (symbol,))
            exists = cur.fetchone()[0] > 0
            if not exists:
                description = asset.get('name', '')
                asset_type = asset.get('class', '')
                live_enabled = 0
                isactive = 0
                try:
                    cur.execute('INSERT INTO symbols (symbol, description, asset_type, live_enabled, isactive) VALUES (%s, %s, %s, %s, %s)',
                                (symbol, description, asset_type, live_enabled, isactive))
                except Exception as e:
                    logger.warning(f'Could not insert {symbol}: {e}')
            # Update all fields from Alpaca
            for k, v in asset.items():
                if k == 'symbol':
                    continue
                try:
                    value = json.dumps(v) if isinstance(v, (dict, list)) else v
                    cur.execute(f'UPDATE symbols SET {k}=%s WHERE symbol=%s', (value, symbol))
                except Exception as e:
                    logger.warning(f'Could not update {k} for {symbol}: {e}')
        conn.commit()
        logger.info('Symbols table updated with Alpaca API data. Missing symbols inserted if needed.')
    except Exception as e:
        logger.error(f"Database error: {e}")
        return 2
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    exit(update_symbols_table_with_alpaca_data())
