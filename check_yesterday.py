#!/usr/bin/env python
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

db_path = Path("docs/data/tradingcopilot.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get schema first
print("Tables in database:")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for table in tables:
    print(f"  {table[0]}")

print("\nrealtime_paper_log columns:")
schema = conn.execute("PRAGMA table_info(realtime_paper_log)").fetchall()
for col in schema:
    print(f"  {col[1]}: {col[2]}")

# Now check yesterday's data
yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
print(f"\n\nChecking missed opportunities for: {yesterday}")
print("=" * 60)

versions = conn.execute("""
    SELECT DISTINCT LOWER(version) as version FROM realtime_paper_log
    WHERE DATE(logged_at) = ?
    ORDER BY version
""", (yesterday,)).fetchall()

if not versions:
    print("No trading activity found yesterday.")
else:
    for version_row in versions:
        v = version_row['version']
        symbols = conn.execute("""
            SELECT DISTINCT symbol, COUNT(*) as count FROM realtime_paper_log
            WHERE DATE(logged_at) = ? AND LOWER(version) = ?
            GROUP BY symbol
            ORDER BY symbol
        """, (yesterday, v)).fetchall()
        
        print(f"\nVersion {v}:")
        print(f"  Symbols traded:")
        for sym_row in symbols:
            print(f"    {sym_row['symbol']}: {sym_row['count']} entries")

conn.close()
