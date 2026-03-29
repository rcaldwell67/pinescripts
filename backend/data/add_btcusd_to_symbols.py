import sqlite3
conn = sqlite3.connect('docs/data/tradingcopilot.db')
c = conn.cursor()
c.execute("INSERT OR IGNORE INTO symbols (symbol, description) VALUES (?, ?)", ('BTCUSD', 'Bitcoin/US Dollar'))
conn.commit()
conn.close()
print("BTCUSD added to symbols table.")
