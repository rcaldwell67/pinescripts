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

# Import symbol_id lookup
from symbol_id_lookup import get_symbol_id

# Import or define all functions and variables needed for Stage 2 from tune_v7_btcusd.py
from tune_v7_btcusd import (
    parse_args, fetch_ohlcv_with_retry, cache_file, stage2_worker, stage2_init
)

def process_stage2_for_chunk(chunk_idx, chunk_file, num_chunks, df, max_workers, save_every, max_mem_mb, max_cpu):
    chunk_df = pd.read_csv(chunk_file)
    if chunk_df.empty:
        print(f"Skipping {chunk_file}: no passing Stage 1 entries.")
        return []
    # Propagate type/side from input if present
    passing_stage1 = []
    for _, row in chunk_df.iterrows():
        param_dict = row.drop(['win_rate']).to_dict()
        # If type/side present in input, keep them for output
        if 'type' in row and pd.notnull(row['type']):
            param_dict['type'] = row['type']
        if 'side' in row and pd.notnull(row['side']):
            param_dict['side'] = row['side']
        passing_stage1.append((param_dict, row['win_rate']))
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
    # Initialize the global DataFrame for stage2_worker
    stage2_init(df)

    # Lookup symbol_id from MariaDB (use symbol from args)
    from tune_v7_btcusd import parse_args
    args = parse_args()
    symbol_id = get_symbol_id(args.symbol)
    if symbol_id is None:
        print(f"Warning: Could not find id for symbol '{args.symbol}' in MariaDB. Using 'UNKNOWN'.")
        symbol_id = 'UNKNOWN'

    for params, win_rate in stage2_param_iter:
        # Use multiprocessing for each param set if needed, but here we keep it simple
        result = stage2_worker((params, win_rate))
        net_return = result.get("net_return", None) if result is not None else None
        # Compute max_drawdown and calmar_ratio if possible
        if result is not None:
            trades = result.get("trades", None)
            # Default type/side to input values if present
            trade_type = params.get('type', None)
            trade_side = params.get('side', None)
            if trades is not None and hasattr(trades, 'empty') and not trades.empty and 'equity' in trades.columns:
                equity_curve = trades['equity']
                max_drawdown = compute_max_drawdown(equity_curve)
                calmar_ratio = compute_calmar_ratio(equity_curve)
                # Try to infer type/side from trades DataFrame if present
                if 'side' in trades.columns:
                    # Use the most common side in trades as the summary
                    trade_side = trades['side'].mode().iloc[0] if not trades['side'].empty else trade_side
                    # Map side to type (Long/Short)
                    if trade_side is not None:
                        trade_type = 'Long' if trade_side.lower() == 'buy' else 'Short' if trade_side.lower() == 'sell' else trade_type
                if 'type' in trades.columns and pd.notnull(trades['type']).any():
                    trade_type = trades['type'].mode().iloc[0]
            else:
                max_drawdown = None
                calmar_ratio = None
            stage2_results.append({
                "symbol_id": symbol_id,
                **params,
                "win_rate": win_rate,
                "net_return": net_return,
                "type": trade_type,
                "side": trade_side,
                "max_drawdown": max_drawdown,
                "calmar_ratio": calmar_ratio,
                "run_timestamp": pd.Timestamp.now()
            })
        completed2 += 1
        if completed2 % save_every == 0:
            tmp_csv2 = "stage2_partial.csv"
            # Ensure columns are ordered as in output_columns
            output_columns = [
                "symbol_id", "lookback", "candle_interval", "macd_fast", "macd_slow", "macd_signal", "stoch_k_len", "stoch_d_len", "cci_len", "ema_fast", "ema_mid", "ema_slow", "rsi_len", "atr_len", "atr_baseline_len", "volume_sma_len", "bb_len", "bb_std_mult", "donchian_len", "adx_len", "atr_percentile_window", "macro_ema_period", "type", "side", "win_rate", "net_return", "max_drawdown", "calmar_ratio", "run_timestamp"
            ]
            df_partial = pd.DataFrame(stage2_results)
            for col in output_columns:
                if col not in df_partial.columns:
                    df_partial[col] = None
            df_partial = df_partial.reindex(columns=output_columns, fill_value=None)
            df_partial.to_csv(tmp_csv2, index=False)
        check_resources2()
    # Filter for both guidelines before returning
    WIN_RATE_TARGET = 65.0
    NET_RETURN_TARGET = 20.0
    filtered_results = [r for r in stage2_results if r["win_rate"] >= WIN_RATE_TARGET and r["net_return"] >= NET_RETURN_TARGET]
    return filtered_results

if __name__ == "__main__":
    args = parse_args()
    symbol = args.symbol
    lookback = args.lookback
    candle_interval = args.candle_interval
    num_chunks = args.num_chunks
    max_workers = 1  # Force single worker for resource safety
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
        # Ensure all relevant columns are present and ordered
        output_columns = [
            "symbol_id", "lookback", "candle_interval", "macd_fast", "macd_slow", "macd_signal", "stoch_k_len", "stoch_d_len", "cci_len", "ema_fast", "ema_mid", "ema_slow", "rsi_len", "atr_len", "atr_baseline_len", "volume_sma_len", "bb_len", "bb_std_mult", "donchian_len", "adx_len", "atr_percentile_window", "macro_ema_period", "type", "side", "win_rate", "net_return", "max_drawdown", "calmar_ratio", "run_timestamp"
        ]
        for col in output_columns:
            if col not in stage2_table.columns:
                stage2_table[col] = None
        stage2_table = stage2_table.reindex(columns=output_columns, fill_value=None)
        out_csv2 = "stage2_results.csv"
        # Always overwrite the output CSV
        stage2_table.to_csv(out_csv2, index=False)
        print(f"Saved Stage 2 results (passing both guidelines) to {out_csv2}")
        if not stage2_table.empty:
            out_csv2_pass = "stage2_passing_params.csv"
            stage2_table.to_csv(out_csv2_pass, index=False)
            print(f"Saved Stage 2 passing parameter sets to {out_csv2_pass}")
            top5 = stage2_table.sort_values("net_return", ascending=False).head(5)
            print("Top 5 parameter sets by Net Return:")
            print(top5)
        else:
            print("No parameter sets met both Stage 1 and Stage 2 guidelines.")
    else:
        print("No Stage 1 passing parameter files with entries found. Skipping Stage 2.")
