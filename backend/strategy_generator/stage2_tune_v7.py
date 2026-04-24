# Stage 2 Tuning Script for v7
# Usage: python stage2_tune_v7.py [args]
# This script performs Stage 2 (Net Return) evaluation on all Stage 1 passing parameter sets.

import os
import pandas as pd
import multiprocessing
import argparse
import glob
import re
import sys

# Import or define all functions and variables needed for Stage 2 from tune_v7_btcusd.py
from tune_v7_btcusd import (
    parse_args, fetch_ohlcv_with_retry, cache_file, stage2_worker, stage2_init
)

def process_stage2_for_chunk(chunk_idx, chunk_file, num_chunks, df, max_workers, save_every, max_mem_mb, max_cpu):
    chunk_df = pd.read_csv(chunk_file)
    if chunk_df.empty:
        print(f"Skipping {chunk_file}: no passing Stage 1 entries.")
        return []
    passing_stage1 = [(row.drop(['win_rate']).to_dict(), row['win_rate']) for _, row in chunk_df.iterrows()]
    stage2_param_iter = passing_stage1
    import psutil
    process2 = psutil.Process(os.getpid())
    def check_resources2():
        mem_mb = process2.memory_info().rss / (1024 * 1024)
        cpu = process2.cpu_percent(interval=0.1) / 100.0
        if mem_mb > max_mem_mb:
            print(f"[Stage 2] Memory usage exceeded {max_mem_mb} MB. Aborting.")
            exit(1)
        if cpu > max_cpu:
            print(f"[Stage 2] CPU usage exceeded {max_cpu*100:.0f}%. Aborting.")
            exit(1)
    stage2_results = []
    completed2 = 0
    for params, win_rate in stage2_param_iter:
        # Use multiprocessing for each param set if needed, but here we keep it simple
        result = stage2_worker((params, win_rate))
        if result is not None:
            stage2_results.append({
                "symbol_id": df.get('symbol', 'UNKNOWN') if isinstance(df, dict) else 'UNKNOWN',
                **params,
                "win_rate": win_rate,
                "net_return": result.get("net_return", None),
                "run_timestamp": pd.Timestamp.now()
            })
        completed2 += 1
        if completed2 % save_every == 0:
            tmp_csv2 = "stage2_partial.csv"
            pd.DataFrame(stage2_results).to_csv(tmp_csv2, index=False)
        check_resources2()
    return stage2_results

if __name__ == "__main__":
    args = parse_args()
    symbol = args.symbol
    lookback = args.lookback
    candle_interval = args.candle_interval
    num_chunks = args.num_chunks
    max_workers = args.max_workers
    save_every = args.save_every
    max_mem_mb = args.max_mem_mb
    max_cpu = args.max_cpu

    # Load or fetch OHLCV data
    if cache_file.exists():
        df = pd.read_csv(cache_file, low_memory=False)
    else:
        df = fetch_ohlcv_with_retry(symbol, lookback=lookback, candle_interval=candle_interval)
        df.to_csv(cache_file, index=False)

    # Always parse all stage1_passing_params_chunk*.csv files for Stage 2
    # Find all Stage 1 output files (chunked or not)
    files = sorted(glob.glob("stage1_passing_params*.csv"))
    all_results = []
    for f in files:
        chunk_results = process_stage2_for_chunk(0, f, 1, df, max_workers, save_every, max_mem_mb, max_cpu)
        all_results.extend(chunk_results)
    if all_results:
        stage2_table = pd.DataFrame(all_results)
        out_csv2 = "stage2_results.csv"
        stage2_table.to_csv(out_csv2, index=False)
        print(f"Saved Stage 2 Net Return results to {out_csv2}")
        NET_RETURN_TARGET = 20.0
        if "net_return" in stage2_table.columns:
            passing_stage2 = stage2_table[stage2_table["net_return"] >= NET_RETURN_TARGET]
            if not passing_stage2.empty:
                out_csv2_pass = "stage2_passing_params.csv"
                passing_stage2.to_csv(out_csv2_pass, index=False)
                print(f"Saved Stage 2 passing parameter sets (Net Return ≥ {NET_RETURN_TARGET}%) to {out_csv2_pass}")
            else:
                print(f"No parameter sets met the Stage 2 Net Return guideline (≥ {NET_RETURN_TARGET}%)")
            top5 = stage2_table.sort_values("net_return", ascending=False).head(5)
            print("Top 5 parameter sets by Net Return:")
            print(top5)
        else:
            print("No 'net_return' column found in Stage 2 results. Skipping Net Return filtering and top 5 display.")
    else:
        print("No Stage 1 passing parameter files with entries found. Skipping Stage 2.")
