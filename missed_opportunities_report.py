#!/usr/bin/env python
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

db_path = Path("docs/data/tradingcopilot.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

print(f"\n📊 MISSED OPPORTUNITIES REPORT - {yesterday}")
print("=" * 70)

# Summary stats
stats = conn.execute("""
    SELECT 
        status,
        COUNT(*) as count,
        COUNT(DISTINCT symbol) as symbols
    FROM realtime_paper_log
    WHERE DATE(logged_at) = ?
    GROUP BY status
    ORDER BY count DESC
""", (yesterday,)).fetchall()

print("\nOVERALL SUMMARY:")
print("-" * 70)
total = 0
for row in stats:
    print(f"  {row['status'].upper():20} {row['count']:3} entries across {row['symbols']} symbols")
    total += row['count']

print(f"  {'TOTAL':20} {total:3} entries")

# Near miss details by symbol
print("\n\nNEAR-MISS OPPORTUNITIES (Trades that almost triggered):")
print("-" * 70)

near_misses = conn.execute("""
    SELECT 
        symbol,
        version,
        COUNT(*) as count,
        MIN(logged_at) as first_time,
        MAX(logged_at) as last_time
    FROM realtime_paper_log
    WHERE DATE(logged_at) = ? AND status = 'near_miss'
    GROUP BY symbol, version
    ORDER BY symbol, version
""", (yesterday,)).fetchall()

if near_misses:
    for nm in near_misses:
        print(f"\n  {nm['symbol']} (v{nm['version']}):")
        print(f"    - Near-miss at {nm['count']} times")
        print(f"    - First: {nm['first_time'].split('T')[1][:8]}")
        print(f"    - Last:  {nm['last_time'].split('T')[1][:8]}")
        
        # Get sample details
        detail = conn.execute("""
            SELECT detail FROM realtime_paper_log
            WHERE DATE(logged_at) = ? AND symbol = ? AND version = ? AND status = 'near_miss'
            LIMIT 1
        """, (yesterday, nm['symbol'], nm['version'])).fetchone()
        
        if detail and detail['detail']:
            d = detail['detail']
            # Extract key reasons
            if 'long:' in d and 'short:' in d:
                parts = d.split('|')
                for part in parts[:2]:  # Show long and short reasons
                    reason = part.strip()
                    if len(reason) > 60:
                        reason = reason[:57] + "..."
                    print(f"      {reason}")
else:
    print("  ✓ No near-misses detected!")

# Schedule misses
print("\n\nSCHEDULE MISSES (Scheduler failures):")
print("-" * 70)

schedule_stats = conn.execute("""
    SELECT 
        COUNT(*) as count,
        COUNT(DISTINCT logged_at) as unique_windows
    FROM realtime_paper_log
    WHERE DATE(logged_at) = ? AND status = 'schedule_miss'
""", (yesterday,)).fetchone()

if schedule_stats['count'] > 0:
    print(f"  - {schedule_stats['count']} schedule miss entries")
    print(f"  - {schedule_stats['unique_windows']} unique scheduler windows affected")
else:
    print("  ✓ No schedule misses!")

# Trading symbols
print("\n\nSYMBOLS MONITORED:")
print("-" * 70)

symbols = conn.execute("""
    SELECT DISTINCT symbol 
    FROM realtime_paper_log
    WHERE DATE(logged_at) = ? AND symbol != '__scheduler__'
    ORDER BY symbol
""", (yesterday,)).fetchall()

print(f"  {', '.join(s['symbol'] for s in symbols)}")

print("\n" + "=" * 70)
print(f"✓ Report generated for {yesterday}\n")

conn.close()
