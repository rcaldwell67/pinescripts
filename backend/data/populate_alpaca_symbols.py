import requests
import sqlite3
import os

from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

# Set your Alpaca API credentials here or use environment variables
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY', 'YOUR_API_KEY')
ALPACA_API_SECRET = os.getenv('ALPACA_API_SECRET', 'YOUR_API_SECRET')
HEADERS = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_API_SECRET
}

# Alpaca API endpoint for assets
ALPACA_ASSETS_URL = 'https://paper-api.alpaca.markets/v2/assets'

# Path to your SQLite DB
DB_PATH = './frontend-react/public/data/tradingcopilot.db'

def fetch_alpaca_symbols():
    resp = requests.get(ALPACA_ASSETS_URL, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

def insert_symbols(symbols):
    import shutil
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for asset in symbols:
        symbol = asset['symbol']
        description = asset.get('name', '')
        asset_type = asset.get('class', '')
        live_enabled = 0
        isactive = 0
        # Insert only if not already present
        cur.execute('SELECT COUNT(*) FROM symbols WHERE symbol = ?', (symbol,))
        if cur.fetchone()[0] == 0:
            cur.execute('INSERT INTO symbols (symbol, description, asset_type, live_enabled, isactive) VALUES (?, ?, ?, ?, ?)',
                        (symbol, description, asset_type, live_enabled, isactive))
        else:
            # Update live_enabled and isactive if symbol already exists
            cur.execute('UPDATE symbols SET live_enabled = ?, isactive = ?, asset_type = ? WHERE symbol = ?', (live_enabled, isactive, asset_type, symbol))
    conn.commit()
    conn.close()
    # Copy updated DB to docs/data location
    docs_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db'))
    try:
        shutil.copyfile(DB_PATH, docs_db_path)
        print(f"Copied updated DB to {docs_db_path}")
    except Exception as e:
        print(f"Warning: Failed to copy DB to docs/data: {e}")

def main():
    print('Fetching Alpaca symbols...')
    symbols = fetch_alpaca_symbols()
    print(f'Fetched {len(symbols)} symbols.')
    insert_symbols(symbols)
    print('Inserted new symbols with active=0.')

if __name__ == '__main__':
    main()
