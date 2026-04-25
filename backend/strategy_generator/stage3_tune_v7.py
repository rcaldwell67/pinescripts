# Stage 3 Tuning Script for v7
# Usage: python stage3_tune_v7.py [args]
# This script performs Stage 3 (e.g., Max Drawdown or further filtering) on all Stage 2 passing parameter sets.


import os
import pandas as pd
import argparse
import glob
import sys
from symbol_id_lookup import get_symbol_id
from v7.apm_v7 import get_v7_params, run_v7_backtest
from tune_v7_btcusd import fetch_ohlcv_with_retry, cache_file

def compute_max_drawdown(equity_curve):
    # Max drawdown as a negative percentage (e.g., -4.2 for -4.2%)
    roll_max = equity_curve.cummax()
    drawdown = (equity_curve - roll_max) / roll_max
    return drawdown.min() * 100 if not drawdown.empty else 0.0

def compute_calmar_ratio(equity_curve):
    # Calmar = CAGR / abs(max_drawdown)
    if len(equity_curve) < 2:
        return 0.0
    start = equity_curve.iloc[0]
    end = equity_curve.iloc[-1]
    n_years = max((equity_curve.index[-1] - equity_curve.index[0]).days / 365.25, 1e-6)
    cagr = ((end / start) ** (1 / n_years)) - 1 if start > 0 else 0.0
    max_dd = abs(compute_max_drawdown(equity_curve)) / 100
    return cagr / max_dd if max_dd > 0 else 0.0

def stage3_worker(args, symbol, df):
    params, win_rate, net_return = args
    # Run v7 backtest for this param set
    v7_params = get_v7_params(symbol)
    v7_params['signal'].update(params)
    trades = run_v7_backtest(df.copy(), v7_params)
    if trades is None or trades.empty or 'equity' not in trades.columns:
        max_drawdown = None
        calmar_ratio = None
    else:
        # Use date-indexed equity curve if available
        if 'date' in trades.columns:
            equity_curve = trades.set_index('date')['equity']
        else:
            equity_curve = trades['equity']
            equity_curve.index = pd.RangeIndex(len(equity_curve))
        max_drawdown = compute_max_drawdown(equity_curve)
        calmar_ratio = compute_calmar_ratio(equity_curve)
    return {**params, "win_rate": win_rate, "net_return": net_return, "max_drawdown": max_drawdown, "calmar_ratio": calmar_ratio}


def process_stage3_for_chunk(chunk_idx, chunk_file, num_chunks, symbol, df, save_every, max_mem_mb, max_cpu):
    chunk_df = pd.read_csv(chunk_file)
    if chunk_df.empty:
        print(f"Skipping {chunk_file}: no passing Stage 2 entries.")
        return []
    passing_stage2 = [(row.drop(['win_rate','net_return']).to_dict(), row['win_rate'], row['net_return']) for _, row in chunk_df.iterrows()]
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
    symbol_id = get_symbol_id(symbol) or 'UNKNOWN'
    stage3_results = []
    completed3 = 0
    for params, win_rate, net_return in passing_stage2:
        result = stage3_worker((params, win_rate, net_return), symbol, df)
        if result is not None:
            stage3_results.append({
                "symbol_id": symbol_id,
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
    parser.add_argument("--symbol", type=str, required=True, help="Trading symbol (e.g., BTC/USD)")
    parser.add_argument("--lookback", type=str, default="YTD")
    parser.add_argument("--candle-interval", type=str, default="15m")
    parser.add_argument("--num-chunks", type=int, default=1)
    parser.add_argument("--save-every", type=int, default=10000)
    parser.add_argument("--max-mem-mb", type=int, default=950)
    parser.add_argument("--max-cpu", type=float, default=0.95)
    parser.add_argument("--equity-only", action="store_true", help="Output only the equity curve for the first parameter set.")
    args = parser.parse_args()
    symbol = args.symbol
    lookback = args.lookback
    candle_interval = args.candle_interval
    num_chunks = args.num_chunks
    save_every = args.save_every
    max_mem_mb = args.max_mem_mb
    max_cpu = args.max_cpu

    # Load or fetch OHLCV data
    if cache_file.exists():
        df = pd.read_csv(cache_file, low_memory=False)
    else:
        df = fetch_ohlcv_with_retry(symbol, lookback=lookback, candle_interval=candle_interval)
        df.to_csv(cache_file, index=False)

    # If equity-only mode, run backtest for first parameter set and output equity curve
    if args.equity_only:
        files = sorted(glob.glob("stage2_passing_params*.csv"))
        found = False
        for f in files:
            chunk_df = pd.read_csv(f)
            if not chunk_df.empty:
                row = chunk_df.iloc[0]
                params = row.drop(['win_rate','net_return']).to_dict()
                v7_params = get_v7_params(symbol)
                v7_params['signal'].update(params)
                trades = run_v7_backtest(df.copy(), v7_params)
                if trades is not None and not trades.empty and 'equity' in trades.columns:
                    equity_curve = trades['equity']
                    equity_curve.to_csv('stage3_equity_curve.csv', index=False)
                    print("Saved equity curve to stage3_equity_curve.csv")
                else:
                    print("No equity curve found for the first parameter set.")
                found = True
                break
        if not found:
            print("No Stage 2 passing parameter sets found.")
        sys.exit(0)

    # Always parse all stage2_passing_params_chunk*.csv files for Stage 3
    files = sorted(glob.glob("stage2_passing_params*.csv"))
    all_results = []
    for f in files:
        chunk_results = process_stage3_for_chunk(0, f, 1, symbol, df, save_every, max_mem_mb, max_cpu)
        all_results.extend(chunk_results)
    if all_results:
        stage3_table = pd.DataFrame(all_results)
        out_csv3 = "stage3_results.csv"
        stage3_table.to_csv(out_csv3, index=False)
        print(f"Saved Stage 3 results to {out_csv3}")
        # Filter by max_drawdown <= 4.5% (i.e., max_drawdown >= -4.5)
        MAX_DRAWDOWN_LIMIT = -4.5
        if "max_drawdown" in stage3_table.columns:
            passing_stage3 = stage3_table[stage3_table["max_drawdown"] >= MAX_DRAWDOWN_LIMIT]
            if not passing_stage3.empty:
                out_csv3_pass = "stage3_passing_params.csv"
                passing_stage3.to_csv(out_csv3_pass, index=False)
                print(f"Saved Stage 3 passing parameter sets to {out_csv3_pass}")
            else:
                print(f"No parameter sets met the Stage 3 guideline (Max Drawdown ≤ 4.5%).")
            top5 = stage3_table.sort_values("max_drawdown", ascending=False).head(5)
            print("Top 5 parameter sets by Max Drawdown:")
            print(top5)
        else:
            print("No Stage 3 metrics found in results. Skipping filtering and top 5 display.")
    else:
        print("No Stage 2 passing parameter files with entries found. Skipping Stage 3.")
