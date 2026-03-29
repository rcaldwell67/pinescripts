import pandas as pd
from apm_v1_backtest import backtest_apm_v1

import os

def load_ohlcv_csv(path):
    df = pd.read_csv(path, parse_dates=['timestamp'])
    df = df.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    })
    return df

if __name__ == '__main__':
    # Use absolute path for data file
    data_path = os.path.join(os.path.dirname(__file__), '../data/btc_usd_5m_ytd.csv')
    df = load_ohlcv_csv(os.path.abspath(data_path))
    trades = backtest_apm_v1(df)
    print(trades)
    trades.to_csv('apm_v1_trades.csv', index=False)
