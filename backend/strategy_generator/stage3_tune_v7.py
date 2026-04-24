# Stage 3 Tuning Script for v7
# Usage: python stage3_tune_v7.py [args]
# This script performs Stage 3 (e.g., Max Drawdown or further filtering) on all Stage 2 passing parameter sets.

import os
import pandas as pd
import multiprocessing
import argparse
import glob
import re
import sys

# Import or define all functions and variables needed for Stage 3 from tune_v7_btcusd.py
# Placeholder: you must implement or import the Stage 3 worker/init and metrics logic
def stage3_worker(args):
    # Implement your Stage 3 evaluation logic here (e.g., max drawdown, calmar ratio)
    params, win_rate, net_return = args
    # Dummy: add placeholder metrics
    max_drawdown = -10.0
    calmar_ratio = 1.5
    return {**params, "win_rate": win_rate, "net_return": net_return, "max_drawdown": max_drawdown, "calmar_ratio": calmar_ratio}

def stage3_init(df):
    pass

def process_stage3_for_chunk(chunk_idx, chunk_file, num_chunks, max_workers, save_every, max_mem_mb, max_cpu):
    chunk_df = pd.read_csv(chunk_file)
    if chunk_df.empty:
        print(f"Skipping {chunk_file}: no passing Stage 2 entries.")
        return []
    passing_stage2 = [(row.drop(['win_rate','net_return']).to_dict(), row['win_rate'], row['net_return']) for _, row in chunk_df.iterrows()]
    stage3_param_iter = passing_stage2
    import psutil
    process3 = psutil.Process(os.getpid())
    def check_resources3():
        mem_mb = process3.memory_info().rss / (1024 * 1024)
        cpu = process3.cpu_percent(interval=0.1) / 100.0
        if mem_mb > max_mem_mb:
            print(f"[Stage 3] Memory usage exceeded {max_mem_mb} MB. Aborting.")
            exit(1)
        if cpu > max_cpu:
            print(f"[Stage 3] CPU usage exceeded {max_cpu*100:.0f}%. Aborting.")
            exit(1)
    stage3_results = []
    completed3 = 0
    for params, win_rate, net_return in stage3_param_iter:
        result = stage3_worker((params, win_rate, net_return))
        if result is not None:
            stage3_results.append({
                "symbol_id": params.get('symbol', 'UNKNOWN'),
                **params,
                "win_rate": win_rate,
                "net_return": net_return,
                "max_drawdown": result.get("max_drawdown", None),
                "calmar_ratio": result.get("calmar_ratio", None),
                "run_timestamp": pd.Timestamp.now()
            })
        completed3 += 1
        if completed3 % save_every == 0:
            tmp_csv3 = "stage3_partial.csv"
            pd.DataFrame(stage3_results).to_csv(tmp_csv3, index=False)
        check_resources3()
    return stage3_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 3 tuning for v7")
    parser.add_argument("--num-chunks", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--save-every", type=int, default=10000)
    parser.add_argument("--max-mem-mb", type=int, default=950)
    parser.add_argument("--max-cpu", type=float, default=0.95)
    args = parser.parse_args()
    num_chunks = args.num_chunks
    max_workers = args.max_workers
    save_every = args.save_every
    max_mem_mb = args.max_mem_mb
    max_cpu = args.max_cpu

    # Always parse all stage2_passing_params_chunk*.csv files for Stage 3
    # Find all Stage 2 output files (chunked or not)
    files = sorted(glob.glob("stage2_passing_params*.csv"))
    all_results = []
    for f in files:
        chunk_results = process_stage3_for_chunk(0, f, 1, max_workers, save_every, max_mem_mb, max_cpu)
        all_results.extend(chunk_results)
    if all_results:
        stage3_table = pd.DataFrame(all_results)
        out_csv3 = "stage3_results.csv"
        stage3_table.to_csv(out_csv3, index=False)
        print(f"Saved Stage 3 results to {out_csv3}")
        # Example: filter by max_drawdown and calmar_ratio
        MAX_DRAWDOWN_LIMIT = -20.0
        CALMAR_MIN = 1.0
        if "max_drawdown" in stage3_table.columns and "calmar_ratio" in stage3_table.columns:
            passing_stage3 = stage3_table[(stage3_table["max_drawdown"] >= MAX_DRAWDOWN_LIMIT) & (stage3_table["calmar_ratio"] >= CALMAR_MIN)]
            if not passing_stage3.empty:
                out_csv3_pass = "stage3_passing_params.csv"
                passing_stage3.to_csv(out_csv3_pass, index=False)
                print(f"Saved Stage 3 passing parameter sets to {out_csv3_pass}")
            else:
                print(f"No parameter sets met the Stage 3 guideline.")
            top5 = stage3_table.sort_values("calmar_ratio", ascending=False).head(5)
            print("Top 5 parameter sets by Calmar ratio:")
            print(top5)
        else:
            print("No Stage 3 metrics found in results. Skipping filtering and top 5 display.")
    else:
        print("No Stage 2 passing parameter files with entries found. Skipping Stage 3.")
