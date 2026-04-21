"""
Strategy parameter tuning and optimization tool for BackTrader strategies.
Supports grid search and random search over parameter ranges.

Usage (example):
    python optimizer.py --symbol BTC/USD --version v6 --param-grid '{"risk": [0.01, 0.02, 0.03], "lookback": [10, 20, 30]}'

This will run backtests for all combinations of risk and lookback values.
"""
import argparse
import itertools
import json
import random
from typing import Any, Dict, List

from backtest_backtrader_alpaca import run_backtest


def grid_search(param_grid: Dict[str, List[Any]], run_fn, run_kwargs: dict) -> List[dict]:
    from v1_params import get_v1_params
    keys = list(param_grid.keys())
    results = []
    for values in itertools.product(*(param_grid[k] for k in keys)):
        params = dict(zip(keys, values))
        run_kwargs_copy = dict(run_kwargs)
        # Start with default v1 params
        merged_params = get_v1_params()
        # Merge grid params into all sections
        for k, v in params.items():
            for section in merged_params:
                if k in merged_params[section]:
                    merged_params[section][k] = v
        run_kwargs_copy['params'] = merged_params
        result = run_fn(**run_kwargs_copy)
        results.append({"params": params, "result": str(result)})
    return results


def random_search(param_grid: Dict[str, List[Any]], run_fn, run_kwargs: dict, n_iter: int = 10) -> List[dict]:
    from v1_params import get_v1_params
    keys = list(param_grid.keys())
    results = []
    for _ in range(n_iter):
        params = {k: random.choice(param_grid[k]) for k in keys}
        run_kwargs_copy = dict(run_kwargs)
        merged_params = get_v1_params()
        for k, v in params.items():
            for section in merged_params:
                if k in merged_params[section]:
                    merged_params[section][k] = v
        run_kwargs_copy['params'] = merged_params
        result = run_fn(**run_kwargs_copy)
        results.append({"params": params, "result": str(result)})
    return results


def main():
    parser = argparse.ArgumentParser(description="Strategy parameter optimizer")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--param-grid", required=True, help="JSON dict of parameter grid, e.g. '{\"risk\": [0.01,0.02], \"lookback\": [10,20]}'.")
    parser.add_argument("--search", choices=["grid", "random"], default="grid")
    parser.add_argument("--n-iter", type=int, default=10, help="Random search iterations")
    args = parser.parse_args()

    import pandas as pd
    # Load OHLCV data for BTC/USD (stage1)
    if args.symbol == "BTC/USD":
        df = pd.read_csv("strategy_generator/btcusd_15m_ytd.csv")
    else:
        raise ValueError(f"No OHLCV data loader for symbol: {args.symbol}")

    param_grid = json.loads(args.param_grid)
    run_kwargs = {"df": df, "symbol": args.symbol, "version": args.version}
    if args.search == "grid":
        results = grid_search(param_grid, run_backtest, run_kwargs)
    else:
        results = random_search(param_grid, run_backtest, run_kwargs, n_iter=args.n_iter)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
