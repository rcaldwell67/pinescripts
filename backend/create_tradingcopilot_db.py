# This script creates the SQLite database and required tables for backtest, paper trading, and live trading results per symbol.
import sqlite3
import os

def create_database(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Backtest Results Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metrics TEXT,
            notes TEXT
        )
    ''')
    # Paper Trading Results Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS paper_trading_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metrics TEXT,
            notes TEXT
        )
    ''')
    # Live Trading Results Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS live_trading_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metrics TEXT,
            notes TEXT
        )
    ''')
    # Symbols Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            description TEXT
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "tradingcopilot.db")
    create_database(db_path)
    print(f"Database created at {db_path}")
