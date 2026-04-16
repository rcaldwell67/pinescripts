"""Fetch and cache active US equity symbols from Alpaca into the database."""

import sqlite3
import os
import sys
from dotenv import load_dotenv

def sync_alpaca_symbols():
    """Fetch active Alpaca assets and store in alpaca_symbols table with type metadata."""
    import logging
    import shutil
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger("sync_alpaca_symbols")
    try:
        import requests
    except ImportError:
        logger.error("Error: requests library not found. Install with: pip install requests")
        sys.exit(1)
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend-react/public/data/tradingcopilot.db'))
    docs_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db'))
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))
    key = os.getenv('ALPACA_PAPER_API_KEY') or os.getenv('ALPACA_API_KEY')
    secret = os.getenv('ALPACA_PAPER_API_SECRET') or os.getenv('ALPACA_API_SECRET')
    if not key or not secret:
        logger.error('Error: Alpaca credentials are required. Set ALPACA_PAPER_API_KEY and ALPACA_PAPER_API_SECRET (or ALPACA_API_KEY/ALPACA_API_SECRET).')
        sys.exit(1)
    logger.info("Fetching Alpaca symbols from paper-api.alpaca.markets...")
    try:
        headers = {
            'APCA-API-KEY-ID': key,
            'APCA-API-SECRET-KEY': secret,
            'Accept': 'application/json',
        }
        endpoints = [
            ('https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity', 'stock'),
            ('https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=crypto', 'crypto'),
        ]
        assets = []
        for url, forced_type in endpoints:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            rows = response.json()
            for asset in rows:
                symbol = asset.get('symbol')
                if not symbol:
                    continue
                name = asset.get('name')
                asset_class = (asset.get('asset_class') or '').lower().strip()
                symbol_type = 'crypto' if (forced_type == 'crypto' or asset_class == 'crypto') else 'stock'
                assets.append((symbol, name, symbol_type))
    except Exception as e:
        logger.error(f"Error fetching from Alpaca: {e}")
        sys.exit(1)
    if not assets:
        logger.error("No assets returned from Alpaca.")
        sys.exit(1)
    
    # De-duplicate by symbol while preserving latest encountered metadata.
    dedup = {}
    for symbol, name, symbol_type in assets:
        dedup[symbol] = (symbol, name, symbol_type)
    symbols_data = sorted(dedup.values(), key=lambda row: row[0])
    
    print(f"Fetched {len(symbols_data)} symbols from Alpaca.")
    
    # Connect to DB and create/populate table
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS alpaca_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                name TEXT,
                type TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        existing_cols = {row[1] for row in c.execute('PRAGMA table_info(alpaca_symbols)').fetchall()}
        if 'type' not in existing_cols:
            c.execute("ALTER TABLE alpaca_symbols ADD COLUMN type TEXT DEFAULT 'stock'")
        # Upsert: insert new, update existing
        for symbol, name, symbol_type in symbols_data:
            c.execute('''
                INSERT INTO alpaca_symbols (symbol, name, type)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                  name=excluded.name,
                  type=excluded.type
            ''', (symbol, name, symbol_type))
        conn.commit()
        synced_count = c.execute('SELECT COUNT(*) FROM alpaca_symbols').fetchone()[0]
        logger.info(f"Synced {synced_count} symbols to database.")
        try:
            shutil.copyfile(db_path, docs_db_path)
            logger.info(f"Copied updated DB to {docs_db_path}")
        except Exception as e:
            logger.warning(f"Warning: Failed to copy DB to docs/data: {e}")
    except Exception as e:
        logger.error(f"Error updating database: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    sync_alpaca_symbols()
