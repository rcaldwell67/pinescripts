# Stage 1 Tuning Script for v7
# Usage: python stage1_tune_v7.py [args]
# This script performs Stage 1 (Win Rate) parameter grid search and outputs passing parameter sets.

import os
import pathlib
import time
import pandas as pd
import itertools
import multiprocessing
import argparse
import sys

# Import or define all functions and variables needed for Stage 1 from tune_v7_btcusd.py
from tune_v7_btcusd import (
    is_valid_combination, parse_args, grid, cache_file, fetch_ohlcv_with_retry, stage1_worker, stage1_init, get_v7_params, run_backtest
)

if __name__ == "__main__":
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

    # Load or fetch OHLCV data
    if cache_file.exists():
        df = pd.read_csv(cache_file, low_memory=False)
    else:
        df = fetch_ohlcv_with_retry(symbol, lookback=lookback, candle_interval=candle_interval)
        df.to_csv(cache_file, index=False)

    # Expand grid and apply pre-filter
    param_grid_all = [t for t in itertools.product(*grid.values()) if is_valid_combination(t)]
    total = len(param_grid_all)
    if sample_fraction < 1.0:
        sample_size = int(total * sample_fraction)
        param_grid_all = random.sample(param_grid_all, sample_size)
        total = len(param_grid_all)


    # For single CSV output, always process the full grid (or sampled grid)
    param_grid_iter = param_grid_all

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
                results.append({
                    "symbol_id": symbol,
                    "lookback": lookback,
                    "candle_interval": candle_interval,
                    **params,
                    "win_rate": win_rate,
                    "run_timestamp": pd.Timestamp.now()
                })
            if completed % save_every == 0:
                tmp_csv = "stage1_partial.csv"
                pd.DataFrame(results).to_csv(tmp_csv, index=False)
            check_resources()

    WIN_RATE_TARGET = 65.0
    passing_stage1 = [row for row in results if row["win_rate"] >= WIN_RATE_TARGET]
    out_csv = "stage1_passing_params.csv"
    if passing_stage1:
        stage1_table = pd.DataFrame(passing_stage1)
        stage1_table.to_csv(out_csv, index=False)
        print(f"Saved passing Stage 1 parameter sets to {out_csv}")
    else:
        print("No parameter sets met the Win Rate guideline.")
