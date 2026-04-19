"""
Tuning script for v7 BTC/USD to meet or exceed strategy guidelines.
Iterates over a parameter grid, runs backtests, and reports the best result.
"""
import itertools
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
}

# Load OHLCV data once
df = fetch_ohlcv("BTC/USD", timespan="YTD")



# Stage 1: Tune for Win Rate only
stage1_best = None
stage1_best_wr = None
for values in itertools.product(*grid.values()):
    params = get_v7_params("BTC/USD")
    for k, v in zip(grid.keys(), values):
        params["signal"][k] = v
    trades = run_backtest(df.copy(), "v7", symbol="BTC/USD")
    if trades.empty:
        continue
    win_rate = float((trades["pnl"] > 0).mean() * 100.0)
    if stage1_best_wr is None or win_rate > stage1_best_wr:
        stage1_best = dict(params["signal"])
        stage1_best_wr = win_rate
    print(f"Stage 1: {params['signal']} => WR={win_rate:.2f}")


print("\nBest Win Rate params:")
print(f"Params: {stage1_best}\nWin Rate: {stage1_best_wr:.2f}%")

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
