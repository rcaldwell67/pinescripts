import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "frontend-react" / "public" / "data" / "tradingcopilot.db"

SQL = """
CREATE TABLE IF NOT EXISTS account (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id TEXT,
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
);
"""

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SQL)
    conn.commit()
    conn.close()
    print("account table created or already exists.")

if __name__ == "__main__":
    main()
