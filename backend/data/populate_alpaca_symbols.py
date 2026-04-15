import requests
import sqlite3
import os
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("populate_alpaca_symbols")

ALPACA_API_KEY = os.getenv('ALPACA_API_KEY') or os.getenv('ALPACA_PAPER_API_KEY')
ALPACA_API_SECRET = os.getenv('ALPACA_API_SECRET') or os.getenv('ALPACA_PAPER_API_SECRET')
HEADERS = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_API_SECRET
}

ALPACA_ASSETS_URL = 'https://paper-api.alpaca.markets/v2/assets'
DB_PATH = './frontend-react/public/data/tradingcopilot.db'

def fetch_alpaca_symbols():
    try:
        resp = requests.get(ALPACA_ASSETS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch Alpaca symbols: {e}")
        return []

def insert_symbols(symbols):
    import shutil
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        for asset in symbols:
            symbol = asset['symbol']
            description = asset.get('name', '')
            asset_type = asset.get('class', '')
            live_enabled = 0
            isactive = 0
            cur.execute('SELECT COUNT(*) FROM symbols WHERE symbol = ?', (symbol,))
            if cur.fetchone()[0] == 0:
                try:
                    cur.execute('INSERT INTO symbols (symbol, description, asset_type, live_enabled, isactive) VALUES (?, ?, ?, ?, ?)',
                                (symbol, description, asset_type, live_enabled, isactive))
                except Exception as e:
                    logger.warning(f'Could not insert {symbol}: {e}')
            else:
                try:
                    cur.execute('UPDATE symbols SET live_enabled = ?, isactive = ?, asset_type = ? WHERE symbol = ?', (live_enabled, isactive, asset_type, symbol))
                except Exception as e:
                    logger.warning(f'Could not update {symbol}: {e}')
        conn.commit()
        logger.info(f'Inserted/updated {len(symbols)} symbols.')
        # Copy updated DB to docs/data location
        docs_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db'))
        try:
            shutil.copyfile(DB_PATH, docs_db_path)
            logger.info(f"Copied updated DB to {docs_db_path}")
        except Exception as e:
            logger.warning(f"Warning: Failed to copy DB to docs/data: {e}")
    except Exception as e:
        logger.error(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

def main():
    logger.info('Fetching Alpaca symbols...')
    symbols = fetch_alpaca_symbols()
    logger.info(f'Fetched {len(symbols)} symbols.')
    insert_symbols(symbols)
    print('Inserted new symbols with active=0.')

if __name__ == '__main__':
    main()
