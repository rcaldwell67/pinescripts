import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "frontend-react" / "public" / "data" / "tradingcopilot.db"

SQL = """
CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT,
  version TEXT,
  mode TEXT,
  metrics TEXT,
  notes TEXT,
  current_equity REAL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SQL)
    conn.commit()
    conn.close()
    print("results table created or already exists.")

if __name__ == "__main__":
    main()
