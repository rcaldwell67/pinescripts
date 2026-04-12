import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "frontend-react" / "public" / "data" / "tradingcopilot.db"

def print_account_info():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT * FROM Account_Info ORDER BY updated_at DESC LIMIT 5")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    for row in rows:
        print(dict(zip(cols, row)))
    conn.close()

if __name__ == "__main__":
    print_account_info()
