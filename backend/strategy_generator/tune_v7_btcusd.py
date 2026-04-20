"""
Tuning script for v7 BTC/USD to meet or exceed strategy guidelines.
Iterates over a parameter grid, runs backtests, and reports the best result.
"""
import itertools
import multiprocessing
import numpy as np
import pandas as pd
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.backtest_backtrader_alpaca import fetch_ohlcv, run_backtest
from backend.strategy_generator.v7.apm_v7 import get_v7_params

# Guideline thresholds
WIN_RATE_TARGET = 65.0
NET_RETURN_TARGET = 15.0
MAX_DD_TARGET = 4.5

# Parameter grid for v7 (expand as needed)
grid = {
    "ema_fast": [5, 8, 13],
    "ema_mid": [13, 21, 34],
    "ema_slow": [34, 55, 89],
    "rsi_len": [10, 14, 21],
    "atr_len": [10, 14, 21],
    "atr_baseline_len": [50, 100, 200],
    "volume_sma_len": [10, 20, 30],
    "macd_fast": [8, 12],
    "macd_slow": [21, 26],
    "macd_signal": [5, 9],
    "stoch_k_len": [7, 14],
    "stoch_d_len": [3, 5],
    "cci_len": [14, 20],
}

<<<<<<< HEAD
# --- OHLCV Data Caching ---
import time
DATA_PATH = os.path.join(os.path.dirname(__file__), "btcusd_15m_ytd.csv")

def fetch_ohlcv_with_retry(symbol, timespan="YTD", max_retries=5, delay=10):
    for attempt in range(max_retries):
        try:
            return fetch_ohlcv(symbol, timespan=timespan)
        except Exception as e:
            if "429" in str(e) or "too many requests" in str(e).lower():
                print(f"Alpaca rate limit hit, retrying in {delay} seconds (attempt {attempt+1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise
    raise RuntimeError("Failed to fetch OHLCV data after retries due to rate limiting.")

def load_or_fetch_ohlcv(symbol, timespan="YTD", path=DATA_PATH):
    if os.path.exists(path):
        print(f"Loading OHLCV data from cache: {path}")
        return pd.read_csv(path, index_col=0, parse_dates=True)
    print("Fetching OHLCV data from API...")
    df = fetch_ohlcv_with_retry(symbol, timespan=timespan)
    df.to_csv(path)
    print(f"Saved OHLCV data to {path}")
    return df

df = load_or_fetch_ohlcv("BTC/USD", timespan="YTD")
=======

# --- Local CSV caching for OHLCV data ---
import pathlib
symbol = "BTC/USD"
timespan = "YTD"
cache_dir = pathlib.Path("./data_cache")
cache_dir.mkdir(exist_ok=True)
cache_file = cache_dir / f"ohlcv_{symbol.replace('/', '-')}_{timespan}.csv"

if cache_file.exists():
    print(f"Loading OHLCV data from cache: {cache_file}")
    import pandas as pd
    df = pd.read_csv(cache_file)
else:
    print(f"Fetching OHLCV data for {symbol} ({timespan}) from API...")
    df = fetch_ohlcv(symbol, timespan=timespan)
    df.to_csv(cache_file, index=False)
    print(f"Saved OHLCV data to cache: {cache_file}")
>>>>>>> 9baba346 (feat: implement local CSV caching for OHLCV data in v7 BTC/USD tuning script)




# --- Multiprocessing helper for Stage 1 ---
def stage1_worker(values):
    params = get_v7_params("BTC/USD")
    for k, v in zip(grid.keys(), values):
        params["signal"][k] = v
    # Pass MACD, Stoch, and CCI params if present
    if "macd_fast" in params["signal"]:
        params["signal"]["macd_fast"] = params["signal"].get("macd_fast", 12)
        params["signal"]["macd_slow"] = params["signal"].get("macd_slow", 26)
        params["signal"]["macd_signal"] = params["signal"].get("macd_signal", 9)
    if "stoch_k_len" in params["signal"]:
        params["signal"]["stoch_k_len"] = params["signal"].get("stoch_k_len", 14)
        params["signal"]["stoch_d_len"] = params["signal"].get("stoch_d_len", 3)
    if "cci_len" in params["signal"]:
        params["signal"]["cci_len"] = params["signal"].get("cci_len", 20)
    trades = run_backtest(df.copy(), "v7", symbol="BTC/USD")
    if trades.empty:
        return None
    win_rate = float((trades["pnl"] > 0).mean() * 100.0)
    return (dict(params["signal"]), win_rate)

if __name__ == "__main__":
    param_grid = list(itertools.product(*grid.values()))
    total = len(param_grid)
    results = []
        # Example: trades = run_backtest(df.copy(), "v7", symbol="BTC/USD", params=params)
        # net_return = ...
    import time
        net_return = 0.0  # TODO: Replace with real calculation
        return (params, net_return)

    if passing_stage1:
        print(f"\nStage 2: Evaluating Net Return for {len(passing_stage1)} parameter sets...")
        # Example: with multiprocessing.Pool() as pool:

        #     stage2_results = pool.map(stage2_worker, passing_stage1)
        for attempt in range(max_retries):
            try:
                return fetch_ohlcv(symbol, timespan=timespan)
            except Exception as e:
                if "429" in str(e) or "too many requests" in str(e).lower():
                    print(f"Alpaca rate limit hit, retrying in {delay} seconds (attempt {attempt+1}/{max_retries})...")
                    time.sleep(delay)
                else:
                    raise
        raise RuntimeError("Failed to fetch OHLCV data after retries due to rate limiting.")

    if cache_file.exists():
        print(f"Loading OHLCV data from cache: {cache_file}")
        import pandas as pd
        df = pd.read_csv(cache_file)
    else:
        print(f"Fetching OHLCV data for {symbol} ({timespan}) from API...")
        df = fetch_ohlcv_with_retry(symbol, timespan=timespan)
        df.to_csv(cache_file, index=False)
        print(f"Saved OHLCV data to cache: {cache_file}")
        # For now, just print placeholder
        for params in passing_stage1:
            print(f"Stage 2: Would evaluate Net Return for {params}")

# Only proceed if Win Rate passes
if stage1_best_wr is not None and stage1_best_wr >= WIN_RATE_TARGET:
    # Stage 2: Tune for Win Rate + Net Return
    stage2_best = None
    stage2_best_result = None
    for values in itertools.product(*grid.values()):
        params = get_v7_params("BTC/USD")
        for k, v in zip(grid.keys(), values):
            params["signal"][k] = v
        trades = run_backtest(df.copy(), "v7", symbol="BTC/USD")
        if trades.empty:
            continue
        start_equity = float(trades["equity"].iloc[0] - trades["pnl"].iloc[0])
        win_rate = float((trades["pnl"] > 0).mean() * 100.0)
        net_return = float((trades["equity"].iloc[-1] / start_equity - 1.0) * 100.0) if start_equity else 0.0
        equity = trades["equity"].astype(float)
        max_dd = float(((equity.cummax() - equity) / equity.cummax() * 100.0).max())
        if win_rate >= WIN_RATE_TARGET and net_return >= NET_RETURN_TARGET:
            if stage2_best_result is None or net_return > stage2_best_result[1]:
                stage2_best = dict(params["signal"])
                stage2_best_result = (win_rate, net_return, max_dd)
        print(f"Stage 2: {params['signal']} => WR={win_rate:.2f} NET={net_return:.2f} DD={max_dd:.2f}")

    print("\nBest Win Rate + Net Return params:")
    if stage2_best_result:
        print(f"Params: {stage2_best}\nWin Rate: {stage2_best_result[0]:.2f}%\nNet Return: {stage2_best_result[1]:.2f}%\nMax DD: {stage2_best_result[2]:.2f}%")
    else:
        print("No parameter set met both Win Rate and Net Return targets.")

    # Only proceed if both Win Rate and Net Return pass
    if stage2_best_result:
        # Stage 3: Tune for all three metrics
        stage3_best = None
        stage3_best_result = None
        for values in itertools.product(*grid.values()):
            params = get_v7_params("BTC/USD")
            for k, v in zip(grid.keys(), values):
                params["signal"][k] = v
            trades = run_backtest(df.copy(), "v7", symbol="BTC/USD")
            if trades.empty:
                continue
            start_equity = float(trades["equity"].iloc[0] - trades["pnl"].iloc[0])
            win_rate = float((trades["pnl"] > 0).mean() * 100.0)
            net_return = float((trades["equity"].iloc[-1] / start_equity - 1.0) * 100.0) if start_equity else 0.0
            equity = trades["equity"].astype(float)
            max_dd = float(((equity.cummax() - equity) / equity.cummax() * 100.0).max())
            if win_rate >= WIN_RATE_TARGET and net_return >= NET_RETURN_TARGET and max_dd <= MAX_DD_TARGET:
                if stage3_best_result is None or max_dd < stage3_best_result[2]:
                    stage3_best = dict(params["signal"])
                    stage3_best_result = (win_rate, net_return, max_dd)
            print(f"Stage 3: {params['signal']} => WR={win_rate:.2f} NET={net_return:.2f} DD={max_dd:.2f}")

        print("\nBest Win Rate + Net Return + Max DD params:")
        if stage3_best_result:
            print(f"Params: {stage3_best}\nWin Rate: {stage3_best_result[0]:.2f}%\nNet Return: {stage3_best_result[1]:.2f}%\nMax DD: {stage3_best_result[2]:.2f}%")
        else:
            print("No parameter set met all three targets.")
            if win_rate >= WIN_RATE_TARGET and net_return >= NET_RETURN_TARGET:
                if stage3_best_result is None or max_dd < stage3_best_result[2]:
                    stage3_best = dict(params["signal"])
                    stage3_best_result = (win_rate, net_return, max_dd)
            print(f"Stage 3: {params['signal']} => WR={win_rate:.2f} NET={net_return:.2f} DD={max_dd:.2f}")

        print("\nBest Win Rate + Net Return + Max DD params:")
        if stage3_best_result and stage3_best_result[0] >= WIN_RATE_TARGET and stage3_best_result[1] >= NET_RETURN_TARGET and stage3_best_result[2] <= MAX_DD_TARGET:
            print(f"Params: {stage3_best}\nWin Rate: {stage3_best_result[0]:.2f}%\nNet Return: {stage3_best_result[1]:.2f}%\nMax DD: {stage3_best_result[2]:.2f}%")
        else:
            print("No parameter set met all three targets. Best found:")
            print(f"Params: {stage3_best}\nWin Rate: {stage3_best_result[0]:.2f}%\nNet Return: {stage3_best_result[1]:.2f}%\nMax DD: {stage3_best_result[2]:.2f}%")
