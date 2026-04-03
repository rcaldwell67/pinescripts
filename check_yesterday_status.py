#!/usr/bin/env python
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

db_path = Path("docs/data/tradingcopilot.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

print(f"Checking statuses recorded on {yesterday}:")
print("=" * 60)

# Get all unique statuses from yesterday
statuses = conn.execute("""
    SELECT DISTINCT status FROM realtime_paper_log
    WHERE DATE(logged_at) = ?
    ORDER BY status
""", (yesterday,)).fetchall()

for status_row in statuses:
    status = status_row['status']
    count = conn.execute("""
        SELECT COUNT(*) as cnt FROM realtime_paper_log
        WHERE DATE(logged_at) = ? AND status = ?
    """, (yesterday, status)).fetchone()['cnt']
    print(f"  {status}: {count} entries")

print("\n\nAll non-scheduler entries from yesterday:")
print("=" * 60)

entries = conn.execute("""
    SELECT logged_at, symbol, version, status, detail 
    FROM realtime_paper_log
    WHERE DATE(logged_at) = ? AND symbol != '__scheduler__'
    ORDER BY logged_at, symbol, version
""", (yesterday,)).fetchall()

if not entries:
    print("No trading activity found.")
else:
    for entry in entries:
        print(f"\n{entry['logged_at']} | {entry['symbol']:10} | v{entry['version']:1} | {entry['status']}")
        if entry['detail']:
            # Print detail on multiple lines if needed
            detail = entry['detail']
            if len(detail) > 80:
                print(f"  Detail: {detail[:77]}...")
            else:
                print(f"  Detail: {detail}")

conn.close()
