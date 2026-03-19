import os
import shutil
import csv
from datetime import datetime
from alpaca-py import Client

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

ALPACA_API_KEY = os.getenv('ALPACA_PAPER_API_KEY')
ALPACA_API_SECRET = os.getenv('ALPACA_PAPER_API_SECRET')
ALPACA_MODE = os.getenv('ALPACA_MODE', 'paper')

# Alpaca endpoint
BASE_URL = 'https://paper-api.alpaca.markets' if ALPACA_MODE == 'paper' else 'https://api.alpaca.markets'

# CSV paths
BTCUSD_CSV = 'docs/data/btcusd/paper_trades.csv'
CLM_CSV = 'docs/data/clm/paper_trades.csv'

# Backup function
def backup_csv(path):
    if os.path.exists(path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{path}.bak_{timestamp}"
        shutil.copy(path, backup_path)
        print(f"Backup created: {backup_path}")

# Fetch trades from Alpaca
def fetch_trades(symbol):
    client = Client(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_MODE=='paper')
    orders = client.get_orders(status='all', symbol=symbol, limit=1000)
    trades = []
    for order in orders:
        trades.append({
            'entry_time': order.submitted_at,
            'exit_time': order.filled_at,
            'direction': order.side,
            'entry': order.limit_price or order.price,
            'exit': order.filled_avg_price,
            'result': order.status,
            'qty': order.qty,
            'pnl': order.filled_avg_price and order.limit_price and (float(order.filled_avg_price) - float(order.limit_price)) * float(order.qty) or '',
        })
    return trades

# Write trades to CSV
def write_trades_csv(path, trades):
    backup_csv(path)
    with open(path, 'w', newline='') as csvfile:
        fieldnames = ['entry_time', 'exit_time', 'direction', 'entry', 'exit', 'result', 'qty', 'pnl']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade)
    print(f"CSV updated: {path}")

if __name__ == '__main__':
    btcusd_trades = fetch_trades('BTCUSD')
    clm_trades = fetch_trades('CLM')
    write_trades_csv(BTCUSD_CSV, btcusd_trades)
    write_trades_csv(CLM_CSV, clm_trades)
    print("Alpaca paper trades synced.")

# To schedule: Use cron or GitHub Actions to run this script periodically.
# Example cron: 0 * * * * /usr/bin/python3 /path/to/fetch_alpaca_paper_trades.py
