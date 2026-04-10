import requests
import sqlite3
import os
from dotenv import load_dotenv
load_dotenv()

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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for asset in symbols:
        symbol = asset['symbol']
        description = asset.get('name', '')
        asset_class = asset.get('class', '')
        # Insert only if not already present
        cur.execute('SELECT COUNT(*) FROM symbols WHERE symbol = ?', (symbol,))
        if cur.fetchone()[0] == 0:
            cur.execute('INSERT INTO symbols (symbol, description, asset_class, active) VALUES (?, ?, ?, 0)',
                        (symbol, description, asset_class))
    conn.commit()
    conn.close()

def main():
    print('Fetching Alpaca symbols...')
    symbols = fetch_alpaca_symbols()
    print(f'Fetched {len(symbols)} symbols.')
    insert_symbols(symbols)
    print('Inserted new symbols with active=0.')

if __name__ == '__main__':
    main()
