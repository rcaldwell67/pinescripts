import sqlite3

conn = sqlite3.connect('docs/data/tradingcopilot.db')

rows = conn.execute(
    """
    SELECT status, COUNT(*)
    FROM realtime_paper_log
    GROUP BY status
    ORDER BY COUNT(*) DESC
    """
).fetchall()
print('realtime_paper_log status counts:')
for s, c in rows:
    print(f'  {s}: {c}')

print('\nlatest realtime_paper_log rows:')
rows = conn.execute(
    """
    SELECT symbol, version, status, detail, logged_at
    FROM realtime_paper_log
    WHERE symbol != '__scheduler__'
    ORDER BY logged_at DESC
    LIMIT 20
    """
).fetchall()
for r in rows:
    print(' ', r)

has_fill = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_fill_events'").fetchone() is not None
has_links = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_order_trade_links'").fetchone() is not None

print('\ncounts:')
print("  paper_trades_source_realtime:", conn.execute("SELECT COUNT(*) FROM trades WHERE mode='paper' AND COALESCE(source,'')='realtime'").fetchone()[0])
print("  paper_fill_events:", conn.execute("SELECT COUNT(*) FROM paper_fill_events").fetchone()[0] if has_fill else 0)
print("  paper_order_links:", conn.execute("SELECT COUNT(*) FROM paper_order_trade_links").fetchone()[0] if has_links else 0)

rows = conn.execute(
    """
    SELECT notes, COUNT(*)
    FROM paper_trading_results
    GROUP BY notes
    ORDER BY COUNT(*) DESC
    """
).fetchall()
print('\npaper_trading_results notes counts:')
for n, c in rows[:20]:
    print(f'  {n}: {c}')

conn.close()
