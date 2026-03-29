"""
Fetch full YTD 5-minute BTCUSD data from Alpaca and save as CSV.
Requires: pip install alpaca-py python-dotenv pandas
"""
import os
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load API keys from .env
load_dotenv()

ALPACA_API_KEY = os.getenv("APCA_API_KEY_ID")
ALPACA_API_SECRET = os.getenv("APCA_API_SECRET_KEY")

print(f"[DEBUG] APCA_API_KEY_ID: {ALPACA_API_KEY}")
print(f"[DEBUG] APCA_API_SECRET_KEY: {ALPACA_API_SECRET[:4]}... (hidden)")

if not ALPACA_API_KEY or not ALPACA_API_SECRET:
    raise ValueError("Alpaca API keys not found in .env file.")


# Use custom API base URL if provided
ALPACA_API_BASE_URL = os.getenv("APCA_API_BASE_URL")
if ALPACA_API_BASE_URL:
    os.environ["APCA_API_BASE_URL"] = ALPACA_API_BASE_URL
    print(f"[DEBUG] Using custom Alpaca API base URL: {ALPACA_API_BASE_URL}")

client = CryptoHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)

# Define date range for YTD
start = datetime(datetime.now().year, 1, 1)
end = datetime.now()

# Fetch 5m bars for BTC/USD (Alpaca symbol: 'BTC/USD')

request_params = CryptoBarsRequest(
    symbol_or_symbols="BTC/USD",
    timeframe=TimeFrame.Minute,
    start=start,
    end=end
)

print(f"Fetching BTC/USD 5m bars from {start} to {end}...")

bars = client.get_crypto_bars(request_params).df

if bars.empty:
    print("No data returned from Alpaca. Check symbol, permissions, and date range.")
else:
    # Reset index and set DatetimeIndex for resampling
    bars = bars.reset_index()
    if 'timestamp' in bars.columns:
        bars['timestamp'] = pd.to_datetime(bars['timestamp'])
        bars = bars.set_index('timestamp')
    else:
        # Fallback: try first column
        bars.iloc[:,0] = pd.to_datetime(bars.iloc[:,0])
        bars = bars.set_index(bars.columns[0])
    # Resample to 5m (use '5min' for pandas >=2.0)
    bars_5m = bars.resample('5min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'trade_count': 'sum'
    })
    bars_5m.dropna(inplace=True)
    # Save to CSV
    csv_path = "backend/data/btc_usd_5m_ytd.csv"
    bars_5m.to_csv(csv_path)
    print(f"Saved {len(bars_5m)} rows to {csv_path}")
