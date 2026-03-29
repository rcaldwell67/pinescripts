"""
Fetch full YTD 5-minute BTCUSD data from yFinance and save as CSV for Backtrader backtesting.
Requires: pip install yfinance pandas
"""
import yfinance as yf
import pandas as pd
from datetime import datetime

# Set symbol and timeframe
yf_symbol = 'BTC-USD'
interval = '5m'


# yFinance 5m data only available for ~60 days
from datetime import timedelta
end_dt = datetime.now()
start_dt = end_dt - timedelta(days=60)
start = start_dt.strftime("%Y-%m-%d")
end = end_dt.strftime("%Y-%m-%d")

print(f"Fetching {yf_symbol} {interval} bars from {start} to {end} via yFinance (max 60 days)...")

data = yf.download(tickers=yf_symbol, interval=interval, start=start, end=end, progress=True)

if data.empty:
    raise RuntimeError("No data returned from yFinance. 5m data is only available for the last 60 days.")

# yFinance returns columns: Open, High, Low, Close, Volume
# Backtrader expects: open, high, low, close, volume, datetime (index)
data = data.rename(columns={
    'Open': 'open',
    'High': 'high',
    'Low': 'low',
    'Close': 'close',
    'Volume': 'volume'
})

# Drop rows with missing data
data.dropna(inplace=True)

# Save to CSV
csv_path = "backend/data/btc_usd_5m_ytd.csv"
data.to_csv(csv_path)
print(f"Saved {len(data)} rows to {csv_path}")
