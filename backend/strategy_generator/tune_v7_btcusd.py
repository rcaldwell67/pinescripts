"""
Tuning script for v7 BTC/USD to meet or exceed strategy guidelines.
Staged optimization: Win Rate → Net Return → Max Drawdown.
Multiprocessing and local CSV caching for efficiency.
"""

import os
import pathlib
import time
import pandas as pd
import itertools
import multiprocessing
import argparse

# --- Argument parsing ---
def parse_args():
    parser = argparse.ArgumentParser(description="Tuning script for v7 BTC/USD with flexible candle interval.")
    parser.add_argument("--symbol", type=str, default="BTC/USD", help="Trading symbol (default: BTC/USD)")
    parser.add_argument("--lookback", type=str, default="YTD", help="Lookback period (e.g., YTD, MTD, 1D)")
    parser.add_argument("--candle-interval", type=str, default="15m", help="Candle interval (e.g., 1m, 5m, 15m, 1h)")
    return parser.parse_args()

args = parse_args()
symbol = args.symbol
lookback = args.lookback
candle_interval = args.candle_interval

# --- User configuration ---
candle_interval = "15m"  # e.g., 15m, 30m, 1h, etc.

# --- Parameter grid (example, expand as needed) ---
grid = {
    "macd_fast": [12, 16],
    "macd_slow": [26, 32],
    "macd_signal": [9],
    "stoch_k_len": [7, 14],
    "stoch_d_len": [3],
    "cci_len": [20],
}

# --- Local CSV caching for OHLCV data with retry logic ---
cache_dir = pathlib.Path("./data_cache")
cache_dir.mkdir(exist_ok=True)
cache_file = cache_dir / f"ohlcv_{symbol.replace('/', '-')}_{lookback}_{candle_interval}.csv"

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backtest_backtrader_alpaca import fetch_ohlcv as fetch_ohlcv_backend


# The backend expects timespan to control both lookback and interval granularity (e.g., "YTD", "30m", etc.)
def fetch_ohlcv(symbol, lookback="YTD", candle_interval="15m"):
    # If candle_interval is a standard lookback (YTD, MTD, etc.), use as timespan; else, treat as interval
    # For 30m, 15m, etc., pass as timespan
    if candle_interval in ["YTD", "MTD", "WTD", "1D", "4H", "1H", "30m", "15m"]:
        return fetch_ohlcv_backend(symbol, timespan=candle_interval)
    else:
        return fetch_ohlcv_backend(symbol, timespan=lookback)

def fetch_ohlcv_with_retry(symbol, lookback="YTD", candle_interval="15m", max_retries=5, delay=10):
    for attempt in range(max_retries):
        try:
            return fetch_ohlcv(symbol, lookback=lookback, candle_interval=candle_interval)
        except Exception as e:
            if "429" in str(e) or "too many requests" in str(e).lower():
                print(f"Alpaca rate limit hit, retrying in {delay} seconds (attempt {attempt+1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise
    raise RuntimeError("Failed to fetch OHLCV data after retries due to rate limiting.")

def get_v7_params(symbol):
    # TODO: Implement or import your parameter template logic
    return {"symbol": symbol, "signal": {}}

def run_backtest(df, version, symbol, params=None):
    # Dummy implementation for demonstration: simulate random trades
    import numpy as np
    n_trades = np.random.randint(10, 50)
    pnl = np.random.normal(loc=0.1, scale=1.0, size=n_trades)
    equity = np.cumsum(pnl) + 10000
    return pd.DataFrame({'pnl': pnl, 'equity': equity})

# --- Stage 1: Win Rate ---
def stage1_worker(values):
    params = get_v7_params(symbol)
    for k, v in zip(grid.keys(), values):
        params["signal"][k] = v
    trades = run_backtest(df.copy(), "v7", symbol=symbol, params=params)
    if trades is None or trades.empty:
        return None
    win_rate = float((trades["pnl"] > 0).mean() * 100.0)
    return (dict(params["signal"]), win_rate)

if __name__ == "__main__":
    # --- Load or fetch OHLCV data ---
    if cache_file.exists():
        print(f"Loading OHLCV data from cache: {cache_file}")
        df = pd.read_csv(cache_file)
    else:
        print(f"Fetching OHLCV data for {symbol} ({lookback}, {candle_interval}) from API...")
        df = fetch_ohlcv_with_retry(symbol, lookback=lookback, candle_interval=candle_interval)
        df.to_csv(cache_file, index=False)
        print(f"Saved OHLCV data to cache: {cache_file}")

    # --- Stage 1: Win Rate ---
    param_grid = list(itertools.product(*grid.values()))
    total = len(param_grid)
    results = []
    completed = 0
    print(f"Stage 1: Evaluating {total} parameter combinations...")
    with multiprocessing.Pool() as pool:
        for result in pool.imap_unordered(stage1_worker, param_grid):
            completed += 1
            if result is not None:
                params, win_rate = result
                results.append(result)
                print(f"Stage 1 [{completed}/{total}]: {params} => WR={win_rate:.2f}")
            else:
                print(f"Stage 1 [{completed}/{total}]: No result (empty trades)")

    # Filter for Win Rate guideline
    WIN_RATE_TARGET = 65.0  # Minimum win rate percentage for passing Stage 1
    passing_stage1 = [params for params, win_rate in results if win_rate >= WIN_RATE_TARGET]
    print(f"\nStage 1 complete. {len(passing_stage1)} parameter sets passed Win Rate ≥ {WIN_RATE_TARGET}%.")
    if passing_stage1:
        print("Sample passing params:")
        for p in passing_stage1[:5]:
            print(p)
    else:
        print("No parameter sets met the Win Rate guideline.")

    # --- Stage 2: Net Return (placeholder) ---
    def stage2_worker(params):
        # TODO: Implement actual Net Return evaluation here
        # Example: trades = run_backtest(df.copy(), "v7", symbol=symbol, params=params)
        # net_return = ...
        net_return = 0.0  # TODO: Replace with real calculation
        return (params, net_return)

    if passing_stage1:
        print(f"\nStage 2: Evaluating Net Return for {len(passing_stage1)} parameter sets...")
        # Example: with multiprocessing.Pool() as pool:
        #     stage2_results = pool.map(stage2_worker, passing_stage1)
        # For now, just print placeholder
        for params in passing_stage1:
            print(f"Stage 2: Would evaluate Net Return for {params}")
