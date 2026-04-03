#!/usr/bin/env python
"""Analyze scheduler gaps in detail."""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

db_path = Path("docs/data/tradingcopilot.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

print(f"\n📅 SCHEDULER GAP ANALYSIS - {yesterday}")
print("=" * 80)

# Get all scheduler entries ordered by time
scheduler_entries = conn.execute("""
    SELECT logged_at 
    FROM realtime_paper_log
    WHERE DATE(logged_at) = ? AND symbol = '__scheduler__'
    ORDER BY logged_at
""", (yesterday,)).fetchall()

print(f"\nTotal scheduler windows: {len(scheduler_entries)}\n")

# Calculate gaps
if len(scheduler_entries) > 1:
    print("TIME GAPS BETWEEN SCHEDULER RUNS:")
    print("-" * 80)
    
    max_gap = 0
    max_gap_start = None
    max_gap_end = None
    
    for i in range(1, len(scheduler_entries)):
        prev_time = datetime.fromisoformat(scheduler_entries[i-1]['logged_at'])
        curr_time = datetime.fromisoformat(scheduler_entries[i]['logged_at'])
        
        gap_seconds = (curr_time - prev_time).total_seconds()
        gap_minutes = gap_seconds / 60
        
        # Flag gaps > 5 minutes (beyond normal 5m cadence)
        if gap_minutes > 5:
            print(f"  {prev_time.strftime('%H:%M:%S')} → {curr_time.strftime('%H:%M:%S')} | Gap: {gap_minutes:6.1f}m ⚠️")
            
            if gap_minutes > max_gap:
                max_gap = gap_minutes
                max_gap_start = prev_time
                max_gap_end = curr_time

print(f"\n  Longest gap: {max_gap:.1f} minutes")
print(f"  From: {max_gap_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"  To:   {max_gap_end.strftime('%Y-%m-%d %H:%M:%S UTC')}")

# Look for schedule_miss entries
print("\n\nSCHEDULE_MISS ENTRIES:")
print("-" * 80)

schedule_misses = conn.execute("""
    SELECT logged_at, detail
    FROM realtime_paper_log
    WHERE DATE(logged_at) = ? AND status = 'schedule_miss'
    ORDER BY logged_at
""", (yesterday,)).fetchall()

print(f"Total schedule_miss entries: {len(schedule_misses)}\n")

if schedule_misses:
    print("Timestamps with schedule_miss status:")
    for i, entry in enumerate(schedule_misses[:5], 1):
        t = entry['logged_at']
        print(f"  {i}. {t}")
        if entry['detail']:
            detail = entry['detail'][:100]
            print(f"     Detail: {detail}...")

if len(schedule_misses) > 5:
    print(f"  ... and {len(schedule_misses) - 5} more")

# Get active versions and symbols
print("\n\nEXECUTION WINDOWS:")
print("-" * 80)

# Show first and last 10 scheduler entries
print("\nFirst 5 scheduler windows:")
for entry in scheduler_entries[:5]:
    t = datetime.fromisoformat(entry['logged_at'])
    print(f"  {t.strftime('%H:%M:%S')}")

print("\nLast 5 scheduler windows:")
for entry in scheduler_entries[-5:]:
    t = datetime.fromisoformat(entry['logged_at'])
    print(f"  {t.strftime('%H:%M:%S')}")

conn.close()
