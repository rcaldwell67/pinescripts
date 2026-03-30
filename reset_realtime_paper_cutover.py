import sqlite3
from pathlib import Path
from datetime import datetime

root = Path(r'd:\OneDrive\codebase\pinescripts-1')
db = root / 'docs' / 'data' / 'tradingcopilot.db'
bak = root / 'docs' / 'data' / f"tradingcopilot.pre_realtime_reset.{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.db"

# Backup first
bak.write_bytes(db.read_bytes())
print('backup:', bak.name)

conn = sqlite3.connect(str(db), timeout=30)
cur = conn.cursor()

print('paper trades before:', cur.execute("SELECT COUNT(*) FROM trades WHERE mode='paper'").fetchone()[0])
print('paper summaries before:', cur.execute("SELECT COUNT(*) FROM paper_trading_results").fetchone()[0])
exists = cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='paper_fill_events'").fetchone()[0]
print('paper_fill_events exists:', exists)
if exists:
    print('paper fill events before:', cur.execute("SELECT COUNT(*) FROM paper_fill_events").fetchone()[0])

cur.execute("DELETE FROM trades WHERE mode='paper'")
cur.execute("DELETE FROM paper_trading_results")
if exists:
    cur.execute("DELETE FROM paper_fill_events")

conn.commit()
try:
    cur.execute("VACUUM")
except Exception as e:
    print('vacuum skipped:', e)

print('paper trades after:', cur.execute("SELECT COUNT(*) FROM trades WHERE mode='paper'").fetchone()[0])
print('paper summaries after:', cur.execute("SELECT COUNT(*) FROM paper_trading_results").fetchone()[0])
if exists:
    print('paper fill events after:', cur.execute("SELECT COUNT(*) FROM paper_fill_events").fetchone()[0])

conn.close()
