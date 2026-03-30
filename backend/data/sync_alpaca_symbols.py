"""Fetch and cache active US equity symbols from Alpaca into the database."""
import sqlite3
import os
import sys

def sync_alpaca_symbols():
    """Fetch active US equity assets from Alpaca and store in alpaca_symbols table."""
    try:
        import requests
    except ImportError:
        print("Error: requests library not found. Install with: pip install requests")
        sys.exit(1)
    
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db'))

    key = os.getenv('ALPACA_PAPER_API_KEY') or os.getenv('ALPACA_API_KEY')
    secret = os.getenv('ALPACA_PAPER_API_SECRET') or os.getenv('ALPACA_API_SECRET')
    if not key or not secret:
        print(
            'Error: Alpaca credentials are required. Set ALPACA_PAPER_API_KEY and '
            'ALPACA_PAPER_API_SECRET (or ALPACA_API_KEY/ALPACA_API_SECRET).'
        )
        sys.exit(1)
    
    print(f"Fetching Alpaca symbols from paper-api.alpaca.markets...")
    try:
        # Fetch active US equities from Alpaca with API authentication.
        response = requests.get(
            'https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity',
            headers={
                'APCA-API-KEY-ID': key,
                'APCA-API-SECRET-KEY': secret,
                'Accept': 'application/json',
            },
            timeout=30
        )
        response.raise_for_status()
        assets = response.json()
    except Exception as e:
        print(f"Error fetching from Alpaca: {e}")
        sys.exit(1)
    
    if not assets:
        print("No assets returned from Alpaca.")
        sys.exit(1)
    
    # Extract symbol and name
    symbols_data = [
        (asset.get('symbol'), asset.get('name'))
        for asset in assets
        if asset.get('symbol')
    ]
    
    print(f"Fetched {len(symbols_data)} symbols from Alpaca.")
    
    # Connect to DB and create/populate table
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    try:
        # Create table if it doesn't exist
        c.execute('''
            CREATE TABLE IF NOT EXISTS alpaca_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                name TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Clear existing data and insert fresh symbols
        c.execute('DELETE FROM alpaca_symbols')
        c.executemany(
            'INSERT INTO alpaca_symbols (symbol, name) VALUES (?, ?)',
            symbols_data
        )
        
        conn.commit()
        synced_count = c.execute('SELECT COUNT(*) FROM alpaca_symbols').fetchone()[0]
        print(f"Synced {synced_count} symbols to database.")
    except Exception as e:
        print(f"Error updating database: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    sync_alpaca_symbols()
