"""
# --- Set memory limit for Stage 1 (Windows: psutil) ---
try:
    import psutil, os
    p = psutil.Process(os.getpid())
    # 1GB memory limit
    p.rlimit(psutil.RLIMIT_AS, (1 * 1024**3, 1 * 1024**3))
except Exception:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (1 * 1024**3, 1 * 1024**3))
    except Exception:
        pass  # If resource/psutil not available or fails, continue without limit
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
    parser.add_argument("--chunk-index", type=int, default=0, help="Index of this chunk (0-based)")
    parser.add_argument("--num-chunks", type=int, default=1, help="Total number of chunks")
    parser.add_argument("--chunk-output", type=str, default=None, help="Optional output CSV for this chunk")

    parser.add_argument("--max-workers", type=int, default=1, help="Maximum parallel worker processes (default: 1)")
    parser.add_argument("--sample-fraction", type=float, default=1.0, help="Fraction of parameter grid to sample (0 < f <= 1.0)")
    parser.add_argument("--save-every", type=int, default=10000, help="Save intermediate results every N parameter sets")
    parser.add_argument("--max-mem-mb", type=int, default=950, help="Max memory (MB) before aborting (default: 950)")
    parser.add_argument("--max-cpu", type=float, default=0.95, help="Max CPU usage (fraction, default: 0.95)")
    return parser.parse_args()


args = parse_args()

symbol = args.symbol
lookback = args.lookback
candle_interval = args.candle_interval
chunk_index = args.chunk_index
num_chunks = args.num_chunks
chunk_output = args.chunk_output
max_workers = args.max_workers
sample_fraction = args.sample_fraction
save_every = args.save_every
max_mem_mb = args.max_mem_mb
max_cpu = args.max_cpu

# --- User configuration ---
candle_interval = "15m"  # e.g., 15m, 30m, 1h, etc.

# --- Parameter grid (expanded for 30m candles, all indicators) ---
grid = {
    # MACD
    "macd_fast": [8, 12, 16, 20],
    "macd_slow": [21, 26, 32, 40],
    "macd_signal": [7, 9, 12],
    # Stochastic
    "stoch_k_len": [10, 14, 21],
    "stoch_d_len": [3, 5, 7],
    # CCI
    "cci_len": [14, 20, 34],
    # EMA
    "ema_fast": [8, 12, 21],
    "ema_mid": [21, 34, 50],
    "ema_slow": [55, 89, 144],
    # RSI
    "rsi_len": [7, 14, 21],
    # ATR
    "atr_len": [7, 14, 21],
    "atr_baseline_len": [60, 100, 200],
    # Volume SMA
    "volume_sma_len": [10, 20, 30],
    # Bollinger Bands
    "bb_len": [14, 20, 34],
    "bb_std_mult": [1.5, 2.0, 2.5],
    # Donchian Channel
    "donchian_len": [14, 20, 34],
    # DMI/ADX
    "adx_len": [7, 14, 21],
    # ATR Percentile Window
    "atr_percentile_window": [60, 120, 240],
    # Macro EMA
    "macro_ema_period": [0, 50, 100],
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
df_worker = None
def stage1_worker(values):
    global df_worker
    params = get_v7_params(symbol)
    for k, v in zip(grid.keys(), values):
        params["signal"][k] = v
    trades = run_backtest(df_worker.copy(), "v7", symbol=symbol, params=params)
    if trades is None or trades.empty:
        return None
    win_rate = float((trades["pnl"] > 0).mean() * 100.0)
    return (dict(params["signal"]), win_rate)

def stage1_init(df):
    global df_worker
    df_worker = df

if __name__ == "__main__":

    import psutil
    import datetime
    process = psutil.Process(os.getpid())
    def log_resources(stage):
        mem_mb = process.memory_info().rss / (1024 * 1024)
        cpu = process.cpu_percent(interval=0.1) / 100.0
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{now}] {stage}: mem={mem_mb:.2f}MB, cpu={cpu:.2f}"
        print(log_line)
        with open("resource_log.txt", "a") as f:
            f.write(log_line + "\n")

    # --- Load or fetch OHLCV data ---
    log_resources("START")
    if cache_file.exists():
        print(f"Loading OHLCV data from cache: {cache_file}")
        df = pd.read_csv(cache_file, low_memory=False)
        log_resources("AFTER CSV LOAD")
    else:
        print(f"Fetching OHLCV data for {symbol} ({lookback}, {candle_interval}) from API...")
        df = fetch_ohlcv_with_retry(symbol, lookback=lookback, candle_interval=candle_interval)
        log_resources("AFTER API FETCH")
        df.to_csv(cache_file, index=False)
        print(f"Saved OHLCV data to cache: {cache_file}")
        log_resources("AFTER CSV SAVE")

    # Log DataFrame info to help debug memory usage
    print(f"DataFrame shape: {df.shape}")
    print(f"DataFrame dtypes:\n{df.dtypes}")
    with open("resource_log.txt", "a") as f:
        f.write(f"DataFrame shape: {df.shape}\n")
        f.write(f"DataFrame dtypes:\n{df.dtypes}\n")
    log_resources("AFTER DF INFO")

    # --- Stage 1: Win Rate ---

    # --- Chunking logic ---

    import random
    param_grid_all = list(itertools.product(*grid.values()))
    total = len(param_grid_all)
    # Sampling
    if sample_fraction < 1.0:
        sample_size = int(total * sample_fraction)
        param_grid_all = random.sample(param_grid_all, sample_size)
        total = len(param_grid_all)
        print(f"Sampling {sample_size} parameter sets from full grid.")
    # Chunking
    if num_chunks > 1:
        chunk_size = (total + num_chunks - 1) // num_chunks
        start = chunk_index * chunk_size
        end = min(start + chunk_size, total)
        param_grid_iter = param_grid_all[start:end]
        print(f"Stage 1: Evaluating chunk {chunk_index+1}/{num_chunks}: {len(param_grid_iter)} of {total} parameter combinations...")
    else:
        param_grid_iter = param_grid_all
        print(f"Stage 1: Evaluating {total} parameter combinations...")


    results = []
    completed = 0
    import psutil
    process = psutil.Process(os.getpid())
    def check_resources():
        mem_mb = process.memory_info().rss / (1024 * 1024)
        cpu = process.cpu_percent(interval=0.1) / 100.0
        if mem_mb > max_mem_mb:
            print(f"Memory usage exceeded {max_mem_mb} MB. Aborting.")
            exit(1)
        if cpu > max_cpu:
            print(f"CPU usage exceeded {max_cpu*100:.0f}%. Aborting.")
            exit(1)

    with multiprocessing.Pool(processes=max_workers, initializer=stage1_init, initargs=(df,)) as pool:
        for result in pool.imap_unordered(stage1_worker, param_grid_iter):
            completed += 1
            if result is not None:
                params, win_rate = result
                results.append(result)
                print(f"Stage 1 [{completed}/{len(param_grid_iter)}]: {params} => WR={win_rate:.2f}")
            else:
                print(f"Stage 1 [{completed}/{len(param_grid_iter)}]: No result (empty trades)")
            if completed % save_every == 0:
                # Save intermediate results
                tmp_csv = chunk_output or f"stage1_partial_{chunk_index+1}_of_{num_chunks}.csv"
                pd.DataFrame([
                    {**params, "win_rate": win_rate} for params, win_rate in results
                ]).to_csv(tmp_csv, index=False)
                print(f"[Checkpoint] Saved {completed} results to {tmp_csv}")
            if completed % 100 == 0:
                log_resources(f"PROGRESS {completed}")
            check_resources()

    # Filter for Win Rate guideline
    WIN_RATE_TARGET = 65.0  # Minimum win rate percentage for passing Stage 1

    # Save all passing Stage 1 parameter sets and their win rates to CSV
    passing_stage1 = [(params, win_rate) for params, win_rate in results if win_rate >= WIN_RATE_TARGET]
    print(f"\nStage 1 chunk complete. {len(passing_stage1)} parameter sets passed Win Rate ≥ {WIN_RATE_TARGET}% in this chunk.")
    if passing_stage1:
        print("Sample passing params:")
        for p, wr in passing_stage1[:5]:
            print(f"{p} => WR={wr:.2f}")
        # Save to chunked CSV
        out_csv = chunk_output or f"stage1_passing_params_chunk{chunk_index+1}_of_{num_chunks}.csv" if num_chunks > 1 else "stage1_passing_params.csv"
        stage1_table = pd.DataFrame([
            {**params, "win_rate": win_rate} for params, win_rate in passing_stage1
        ])
        stage1_table.to_csv(out_csv, index=False)
        print(f"Saved passing Stage 1 parameter sets to {out_csv}")
    else:
        print("No parameter sets met the Win Rate guideline in this chunk.")

    # --- Stage 2: Net Return (placeholder) ---
    def stage2_worker(args):
        params, win_rate = args
        trades = run_backtest(df.copy(), "v7", symbol=symbol, params=params)
        if trades is None or trades.empty:
            net_return = float('-inf')
        else:
            net_return = float(trades["pnl"].sum())
        return {**params, "win_rate": win_rate, "net_return": net_return}

    if passing_stage1:
        print(f"\nStage 2: Evaluating Net Return for {len(passing_stage1)} parameter sets...")
        with multiprocessing.Pool(processes=1) as pool:
            stage2_results = list(pool.imap_unordered(stage2_worker, passing_stage1))
        # Save Stage 2 results to CSV
        stage2_table = pd.DataFrame(stage2_results)
        stage2_table.to_csv("stage2_results.csv", index=False)
        print("Saved Stage 2 Net Return results to stage2_results.csv")
        # Print top 5 by net return
        top5 = stage2_table.sort_values("net_return", ascending=False).head(5)
        print("Top 5 parameter sets by Net Return:")
        print(top5)
