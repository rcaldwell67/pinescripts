def compute_max_drawdown(equity_curve):
    roll_max = equity_curve.cummax()
    drawdown = (equity_curve - roll_max) / roll_max
    return drawdown.min() * 100 if not drawdown.empty else 0.0

def compute_calmar_ratio(equity_curve):
    if len(equity_curve) < 2:
        return 0.0
    start = equity_curve.iloc[0]
    end = equity_curve.iloc[-1]
    n_years = max((equity_curve.index[-1] - equity_curve.index[0]).days / 365.25, 1e-6) if hasattr(equity_curve.index, 'days') else max(len(equity_curve) / 252, 1e-6)
    cagr = ((end / start) ** (1 / n_years)) - 1 if start > 0 else 0.0
    max_dd = abs(compute_max_drawdown(equity_curve)) / 100
    return cagr / max_dd if max_dd > 0 else 0.0
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
import random

# Import symbol_id lookup
from symbol_id_lookup import get_symbol_id

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
    max_workers = 1  # Force single worker for resource safety
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

    # Lookup symbol_id from MariaDB
    symbol_id = get_symbol_id(symbol)
    if symbol_id is None:
        print(f"Warning: Could not find id for symbol '{symbol}' in MariaDB. Using 'UNKNOWN'.")
        symbol_id = 'UNKNOWN'

    # Expand grid and apply pre-filter
    param_grid_all = [t for t in itertools.product(*grid.values()) if is_valid_combination(t)]
    total = len(param_grid_all)
    if sample_fraction < 1.0:
        sample_size = int(total * sample_fraction)
        param_grid_all = random.sample(param_grid_all, sample_size)
        total = len(param_grid_all)



    # --- Chunked processing to avoid memory limit ---
    CHUNK_SIZE = 1000  # You can adjust this value as needed
    total = len(param_grid_all)
    num_chunks = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
    tmp_csv = "stage1_partial.csv"
    # Remove old partial file if exists
    if os.path.exists(tmp_csv):
        os.remove(tmp_csv)

    import psutil
    process = psutil.Process(os.getpid())
    def check_resources():
        mem_mb = process.memory_info().rss / (1024 * 1024)
        if mem_mb > max_mem_mb:
            print(f"Memory usage exceeded {max_mem_mb} MB. Aborting.")
            exit(1)

    completed = 0
    for chunk_idx in range(num_chunks):
        start = chunk_idx * CHUNK_SIZE
        end = min((chunk_idx + 1) * CHUNK_SIZE, total)
        chunk = param_grid_all[start:end]
        results = []
        with multiprocessing.Pool(processes=max_workers, initializer=stage1_init, initargs=(df,)) as pool:
            for result in pool.imap_unordered(stage1_worker, chunk):
                completed += 1
                if result is not None:
                    params, win_rate = result
                    v7_params = get_v7_params(symbol)
                    v7_params['signal'].update(params)
                    trades = run_backtest(df.copy(), "v7", symbol=symbol, params=params)
                    if trades is not None and not trades.empty and 'equity' in trades.columns:
                        equity_curve = trades['equity']
                        max_drawdown = compute_max_drawdown(equity_curve)
                        calmar_ratio = compute_calmar_ratio(equity_curve)
                        start_equity = float(equity_curve.iloc[0])
                        end_equity = float(equity_curve.iloc[-1])
                        net_return = ((end_equity / start_equity) - 1.0) * 100 if start_equity else 0.0
                    else:
                        max_drawdown = None
                        calmar_ratio = None
                        net_return = None
                    results.append({
                        "symbol_id": symbol_id,
                        "lookback": lookback,
                        "candle_interval": candle_interval,
                        **params,
                        "win_rate": win_rate,
                        "net_return": net_return,
                        "max_drawdown": max_drawdown,
                        "calmar_ratio": calmar_ratio,
                        "run_timestamp": pd.Timestamp.now()
                    })
                if completed % save_every == 0:
                    pd.DataFrame(results).to_csv(tmp_csv, mode='a', header=not os.path.exists(tmp_csv), index=False)
                    results = []  # Clear memory
                check_resources()
        # Write any remaining results for this chunk
        if results:
            pd.DataFrame(results).to_csv(tmp_csv, mode='a', header=not os.path.exists(tmp_csv), index=False)
        results = []  # Clear memory
        check_resources()

    WIN_RATE_TARGET = 65.0
    passing_stage1 = [row for row in results if row["win_rate"] >= WIN_RATE_TARGET]
    out_csv = "stage1_passing_params.csv"
    if passing_stage1:
        stage1_table = pd.DataFrame(passing_stage1)
        # Standardized output columns for all stages
        output_columns = [
            "symbol_id", "lookback", "candle_interval",
            "macd_fast", "macd_slow", "macd_signal", "stoch_k_len", "stoch_d_len", "cci_len", "ema_fast", "ema_mid", "ema_slow", "rsi_len", "atr_len", "atr_baseline_len", "volume_sma_len", "bb_len", "bb_std_mult", "donchian_len", "adx_len", "atr_percentile_window", "macro_ema_period",
            "type", "side", "win_rate", "net_return", "max_drawdown", "calmar_ratio", "run_timestamp"
        ]
        for col in output_columns:
            if col not in stage1_table.columns:
                stage1_table[col] = None
        stage1_table = stage1_table.reindex(columns=output_columns, fill_value=None)
        # Always overwrite the output CSV
        stage1_table.to_csv(out_csv, index=False)
        print(f"Saved passing Stage 1 parameter sets to {out_csv}")
