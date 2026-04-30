import os
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import yfinance as yf
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_API_SECRET = os.getenv('ALPACA_API_SECRET')

# Alpaca client setup
def get_alpaca_client():
    return StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)

def fetch_alpaca_bars(symbol, start, end, timeframe='1Day'):
    client = get_alpaca_client()
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end
    )
    bars = client.get_stock_bars(request)
    df = bars.df
    return df

def fetch_yfinance_bars(symbol, start, end, interval='1d'):
    data = yf.download(symbol, start=start, end=end, interval=interval)
    return data

if __name__ == '__main__':
    # Example usage
    print('Alpaca bars:')
    # print(fetch_alpaca_bars('AAPL', '2024-01-01', '2024-01-31'))
    print('YFinance bars:')
    print(fetch_yfinance_bars('AAPL', '2024-01-01', '2024-01-31'))
