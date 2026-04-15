import requests
import os
import sqlite3
import json

# Set Alpaca API credentials
ALPACA_API_KEY = os.getenv('ALPACA_PAPER_API_KEY', 'PKA6JVXS7FYDSO7RWFUCLBVZPD')
ALPACA_API_SECRET = os.getenv('ALPACA_PAPER_API_SECRET', 'J285cmRTWHuGgRKCVke297s4ouGDazGydFft3RADbZV7')
HEADERS = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_API_SECRET
}

ALPACA_ASSETS_URL = 'https://paper-api.alpaca.markets/v2/assets'
DB_PATH = './frontend-react/public/data/tradingcopilot.db'

def update_symbols_table_with_alpaca_data():
    resp = requests.get(ALPACA_ASSETS_URL, headers=HEADERS)
    resp.raise_for_status()
    assets = resp.json()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for asset in assets:
        symbol = asset['symbol']
        # Check if symbol exists
        cur.execute('SELECT COUNT(*) FROM symbols WHERE symbol = ?', (symbol,))
        exists = cur.fetchone()[0] > 0
        if not exists:
            # Insert new symbol with basic fields
            description = asset.get('name', '')
            asset_type = asset.get('class', '')
            live_enabled = 0
            isactive = 0
            try:
                cur.execute('INSERT INTO symbols (symbol, description, asset_type, live_enabled, isactive) VALUES (?, ?, ?, ?, ?)',
                            (symbol, description, asset_type, live_enabled, isactive))
            except Exception as e:
                print(f'Could not insert {symbol}: {e}')
        # Update all fields from Alpaca
        for k, v in asset.items():
            if k == 'symbol':
                continue
            try:
                value = json.dumps(v) if isinstance(v, (dict, list)) else v
                cur.execute(f'UPDATE symbols SET {k}=? WHERE symbol=?', (value, symbol))
            except Exception as e:
                print(f'Could not update {k} for {symbol}: {e}')
    conn.commit()
    conn.close()
    print('Symbols table updated with Alpaca API data. Missing symbols inserted if needed.')

if __name__ == '__main__':
    update_symbols_table_with_alpaca_data()
