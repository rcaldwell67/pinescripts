# This script alters the symbols table to add all columns required by update_symbols_with_alpaca_data.py
import sqlite3
import os

def migrate_symbols_table(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Add missing columns if they do not exist
    columns = [
        ('isactive', 'INTEGER DEFAULT 0'),
        ('class', 'TEXT'),
        ('exchange', 'TEXT'),
        ('name', 'TEXT'),
        ('status', 'TEXT'),
        ('tradable', 'INTEGER'),
        ('marginable', 'INTEGER'),
        ('maintenance_margin_requirement', 'REAL'),
        ('margin_requirement_long', 'REAL'),
        ('margin_requirement_short', 'REAL'),
        ('shortable', 'INTEGER'),
        ('easy_to_borrow', 'INTEGER'),
        ('fractionable', 'INTEGER'),
        ('attributes', 'TEXT'),
        ('min_order_size', 'REAL'),
        ('min_trade_increment', 'REAL'),
        ('price_increment', 'REAL')
    ]
    for col, coltype in columns:
        try:
            c.execute(f"ALTER TABLE symbols ADD COLUMN {col} {coltype}")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f'Could not add column {col}: {e}')
    conn.commit()
    conn.close()
    print('Migration complete: symbols table updated.')

if __name__ == '__main__':
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend-react/public/data/tradingcopilot.db'))
    migrate_symbols_table(db_path)
