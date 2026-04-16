# This script creates the SQLite database and required tables for backtest, paper trading, and live trading results per symbol.
import sqlite3
import os

def create_database(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    # Use DELETE (rollback) journal mode so the .db file is fully self-contained
    # and can be loaded by sql.js in the browser without needing -wal/-shm files.
    conn.execute("PRAGMA journal_mode=DELETE")
    c = conn.cursor()
    # Alpaca Symbols Table (for sync and migration)
    c.execute('''
        CREATE TABLE IF NOT EXISTS alpaca_symbols (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            type TEXT DEFAULT 'stock'
        )
    ''')
    # Backtest Results Table (add version)
    c.execute('''
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT 'v6',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metrics TEXT,
            notes TEXT,
            current_equity REAL
        )
    ''')
    # Paper Trading Results Table (add version)
    c.execute('''
        CREATE TABLE IF NOT EXISTS paper_trading_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT 'v6',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metrics TEXT,
            notes TEXT,
            current_equity REAL
        )
    ''')
    # Live Trading Results Table (add version)
    c.execute('''
        CREATE TABLE IF NOT EXISTS live_trading_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT 'v6',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metrics TEXT,
            notes TEXT,
            current_equity REAL
        )
    ''')
    # Symbols Table (add asset_type)
    c.execute('''
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            description TEXT,
            asset_type TEXT DEFAULT 'crypto',
            live_enabled INTEGER NOT NULL DEFAULT 1
        )
    ''')
    # Audit Log Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            user TEXT,
            action TEXT NOT NULL,
            target_table TEXT,
            target_id INTEGER,
            details TEXT
        )
    ''')
    conn.commit()
    # Individual Trades Table (backtest, paper, live)
    c.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT 'v1',
            mode TEXT NOT NULL DEFAULT 'backtest',
            entry_time DATETIME,
            exit_time DATETIME,
            direction TEXT,
            entry_price REAL,
            exit_price REAL,
            result TEXT,
            pnl_pct REAL,
            dollar_pnl REAL,
            equity REAL,
            source TEXT
        )
    ''')
    # Chart OHLCV bars — one row per (symbol, unix-second timestamp)
    c.execute('''
        CREATE TABLE IF NOT EXISTS chart_data (
            symbol TEXT    NOT NULL,
            t      INTEGER NOT NULL,
            o      REAL    NOT NULL,
            h      REAL    NOT NULL,
            l      REAL    NOT NULL,
            c      REAL    NOT NULL,
            v      REAL    NOT NULL,
            PRIMARY KEY (symbol, t)
        )
    ''')
    # One metadata row per symbol — tracks when bars were last fetched
    c.execute('''
        CREATE TABLE IF NOT EXISTS chart_meta (
            symbol       TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL
        )
    ''')
    # Account Info Table (Alpaca paper/live account snapshot)
    c.execute('''
        CREATE TABLE IF NOT EXISTS Account_Info (
            account_id TEXT PRIMARY KEY,
            account_number TEXT,
            account_mode TEXT,
            currency TEXT,
            status TEXT,
            beginning_balance REAL,
            current_balance REAL,
            buying_power REAL,
            cash REAL,
            last_event TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    
    # Paper Trading Order/Fill Tracking Tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS paper_fill_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id TEXT UNIQUE NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            qty REAL,
            price REAL,
            transaction_time TEXT,
            order_id TEXT,
            raw_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS paper_order_trade_links (
            order_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            version TEXT NOT NULL,
            trade_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS paper_order_events (
            event_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            symbol TEXT,
            status TEXT,
            event_type TEXT,
            event_time TEXT,
            qty REAL,
            notional REAL,
            filled_qty REAL,
            submitted_at TEXT,
            raw_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    
    # Live Trading Order/Fill Tracking Tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS live_fill_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id TEXT UNIQUE NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            qty REAL,
            price REAL,
            transaction_time TEXT,
            order_id TEXT,
            raw_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS live_order_trade_links (
            order_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            version TEXT NOT NULL,
            trade_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS live_order_events (
            event_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            symbol TEXT,
            status TEXT,
            event_type TEXT,
            event_time TEXT,
            qty REAL,
            notional REAL,
            filled_qty REAL,
            submitted_at TEXT,
            raw_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    import shutil
    db_path = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "tradingcopilot.db")
    public_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend-react/public/data/tradingcopilot.db'))
    create_database(db_path)
    print(f"Database created at {db_path}")
    # Copy to frontend-react/public/data
    try:
        shutil.copyfile(db_path, public_db_path)
        print(f"Copied DB to {public_db_path}")
    except Exception as e:
        print(f"Warning: Failed to copy DB to frontend-react/public/data: {e}")
