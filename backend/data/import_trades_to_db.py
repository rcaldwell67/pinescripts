"""
Import individual trade CSV files into the trades table in tradingcopilot.db.
Maps CSV columns to the trades table schema and avoids duplicate imports.

Usage:
    python import_trades_to_db.py

Add new CSV files to TRADE_FILES to import additional symbols/versions.
"""
import csv
import sqlite3
import os

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/data/tradingcopilot.db'))

# Each entry maps a CSV file to symbol + version + mode.
# Uses root-level naming convention apm_v*_trades.csv for BTC_USD.
TRADE_FILES = [
    {
        'csv': os.path.abspath(os.path.join(os.path.dirname(__file__), f'../../apm_{version}_trades.csv')),
        'symbol': 'BTC_USD',
        'version': version,
        'mode': 'backtest',
    }
    for version in ('v1', 'v2', 'v3', 'v4', 'v5', 'v6')
]

# CSV column → DB column mapping (columns not listed here are skipped)
CSV_TO_DB = {
    'entry_time':  'entry_time',
    'exit_time':   'exit_time',
    'direction':   'direction',
    'entry':       'entry_price',
    'exit':        'exit_price',
    'result':      'result',
    'pnl_pct':     'pnl_pct',
    'dollar_pnl':  'dollar_pnl',
    'equity':      'equity',
}


def ensure_trades_table(conn):
    conn.execute('''
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
            equity REAL
        )
    ''')
    conn.commit()


def import_csv(conn, csv_path, symbol, version, mode):
    if not os.path.exists(csv_path):
        print(f'WARNING: {csv_path} not found, skipping.')
        return 0

    # Delete existing rows for this symbol/version/mode to allow re-import
    conn.execute(
        'DELETE FROM trades WHERE symbol = ? AND version = ? AND mode = ?',
        (symbol, version, mode)
    )

    db_cols = ['symbol', 'version', 'mode'] + list(CSV_TO_DB.values())
    placeholders = ', '.join(['?'] * len(db_cols))
    insert_sql = f'INSERT INTO trades ({", ".join(db_cols)}) VALUES ({placeholders})'

    count = 0
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            values = [symbol, version, mode]
            for csv_col, db_col in CSV_TO_DB.items():
                val = row.get(csv_col, None)
                if val == '' or val is None:
                    values.append(None)
                else:
                    try:
                        values.append(float(val) if '.' in val or 'e' in val.lower() else val)
                    except (ValueError, AttributeError):
                        values.append(val)
            conn.execute(insert_sql, values)
            count += 1

    conn.commit()
    return count


def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_trades_table(conn)

    for entry in TRADE_FILES:
        n = import_csv(conn, entry['csv'], entry['symbol'], entry['version'], entry['mode'])
        print(f"Imported {n} trades for {entry['symbol']} {entry['version']} ({entry['mode']}) from {entry['csv']}")

    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
