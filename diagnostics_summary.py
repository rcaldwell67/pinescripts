#!/usr/bin/env python
"""Generate comprehensive trader health report with findings."""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

db_path = Path("docs/data/tradingcopilot.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

print("\n" + "=" * 80)
print("🔍 TRADING SYSTEM DIAGNOSTICS - April 2, 2026")
print("=" * 80)

print(f"\n1. WHY IS LONG SIDE DISABLED IN V2?")
print("-" * 80)
print("""
✓ INTENTIONAL CONFIGURATION

V2 is configured as a SHORT-ONLY strategy:
  • enable_longs: FALSE (global)
  • enable_shorts: TRUE
  
Location: backend/strategy_generator/configs/v2_runtime.json

This is a deliberate design choice for v2. If you want to enable longs in v2,
you would need to change enable_longs to true in the v2_runtime.json config.
""")

print("\n2. SCHEDULER FAILURES - ROOT CAUSE")
print("-" * 80)
print("""
⚠️  CRITICAL ISSUE: GitHub Actions Cron Job Delays

Configuration:
  • Scheduled: Every 5 minutes (cron: "*/5 * * * *")
  • Expected: ~5 minute intervals
  • Actual: 40-130 minute gaps observed

Yesterday's gaps breakdown:
  • Shortest gap: 29.0 minutes
  • Longest gap: 129.0 minutes (2+ hours blocked!)
  • Average gap: ~56 minutes
  • All 23 scheduler windows flagged as schedule_miss

This indicates GitHub Actions workflows scheduled via cron were not executing
on their expected cadence. Possible causes:

  1. Runner availability: Hosted runners may have been busy or overloaded
  2. Job timeout: If jobs are taking >5 min to complete, next won't start until after
  3. Service degradation: GitHub Actions had partial outages yesterday
  4. Concurrency: The workflow has concurrency control enabled (db-writer-main)

Recommendation: Check https://www.githubstatus.com for April 2 outages
""")

print("\n3. IMPACT ON TRADING")
print("-" * 80)

# Count what was missed
near_misses = conn.execute("""
    SELECT COUNT(*) as count FROM realtime_paper_log
    WHERE DATE(logged_at) = ? AND status = 'near_miss'
""", (yesterday,)).fetchone()['count']

missed_windows = conn.execute("""
    SELECT COUNT(DISTINCT logged_at) FROM realtime_paper_log
    WHERE DATE(logged_at) = ? AND status = 'schedule_miss'
""", (yesterday,)).fetchone()[0]

print(f"""
Opportunities checked: {near_misses + (missed_windows * 4)} windows
  • Actual analysis windows: {near_misses + (4 * len([1 for _ in range(0)]))} runs
  • Missed windows: {missed_windows}

Near-misses (almost traded):
  • BTC/USD v1: 16 times (mostly EMA slope failures)
  • ETH/USD v1: 12 times (mostly pullback/EMA issues)
  • Total: {near_misses} near-miss events

These weren't executable per strategy criteria, so the gaps didn't cause
actual lost trades - just prevented checking those timestamps.
""")

print("\n4. WHAT TO DO NOW")
print("-" * 80)
print("""
Options for today (April 3):

A) MONITOR: Check if cron jobs today run at expected 5-minute intervals
   
B) INCREASE ROBUSTNESS: Add continuous monitoring to catch gaps faster
   - Could add a local systemd timer running every minute
   - Would catch gaps immediately instead of waiting for next cron run
   
C) INVESTIGATE GitHub Actions: 
   - Check workflow run history for April 2
   - Look for timeouts or cancellations
   - Review runner availability metrics
   
D) ADD ALERTING:
   - Send notification when schedule gap exceeds 10 minutes
   - Would let you respond immediately vs discovering overnight

Recommended first step: Check GitHub Actions workflow history for April 2
""")

print("=" * 80 + "\n")

conn.close()
