import sys

import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import List

import alpaca_trade_api as tradeapi
import os
import pandas as pd
import numpy as np
import json


# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

app = FastAPI()

# Supported timeframes
TIMEFRAMES = ["5m", "10m", "15m", "30m", "1h", "1d"]

# Support both paper and live trading credentials
ALPACA_MODE = os.getenv("ALPACA_MODE", "paper").lower()
if ALPACA_MODE == "live":
    ALPACA_API_KEY = os.getenv("ALPACA_LIVE_API_KEY")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_LIVE_API_SECRET")
    ALPACA_BASE_URL = os.getenv("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets")
else:
    ALPACA_API_KEY = os.getenv("ALPACA_PAPER_API_KEY")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_PAPER_API_SECRET")
    ALPACA_BASE_URL = os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets")

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

class BacktestRequest(BaseModel):
    symbol: str
    timeframes: List[str] = TIMEFRAMES

def get_alpaca_api():
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Alpaca API keys not set.")
    return tradeapi.REST(
        key_id=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
        base_url=ALPACA_BASE_URL
    )


def run_backtest(df: pd.DataFrame, fast: int, slow: int) -> dict:
    # Moving average crossover with parameterized windows
    if fast >= slow:
        return {"error": "fast window must be less than slow window"}
    df = df.copy()
    df['sma_fast'] = df['c'].rolling(window=fast).mean()
    df['sma_slow'] = df['c'].rolling(window=slow).mean()
    df['signal'] = np.where(df['sma_fast'] > df['sma_slow'], 1, 0)
    df['position'] = df['signal'].diff().fillna(0)
    entry_price = None
    returns = []
    for idx, row in df.iterrows():
        if row['position'] == 1:
            entry_price = row['c']
        elif row['position'] == -1 and entry_price is not None:
            returns.append((row['c'] - entry_price) / entry_price)
            entry_price = None
    net_return = np.sum(returns) if returns else 0
    win_rate = np.mean([r > 0 for r in returns]) if returns else 0
    return {
        "trades": len(returns),
        "net_return": float(net_return),
        "win_rate": float(win_rate),
        "returns": returns,
        "fast": fast,
        "slow": slow
    }

def optimize_strategy(df: pd.DataFrame, net_return_target=0.2):
    best_result = None
    best_params = None
    for fast in range(5, 21, 2):
        for slow in range(fast+2, 51, 2):
            result = run_backtest(df, fast, slow)
            if "error" in result:
                continue
            if best_result is None or result['net_return'] > best_result['net_return']:
                best_result = result
                best_params = (fast, slow)
    if best_result and best_result['net_return'] >= net_return_target:
        best_result['meets_target'] = True
    elif best_result:
        best_result['meets_target'] = False
    return best_result if best_result else {"error": "No valid strategy found"}


@app.post("/api/backtest")
def backtest_symbol(req: BacktestRequest):
    return run_backtest_for_symbol(req.symbol, req.timeframes)



def run_backtest_for_symbol(symbol, timeframes=TIMEFRAMES):
    api = get_alpaca_api()
    summary = {}
    for tf in timeframes:
        print(f"[INFO] Processing {symbol} {tf}")
        try:
            bars = api.get_bars(symbol, tf, limit=500)
            data = [{
                't': bar.t,
                'o': bar.o,
                'h': bar.h,
                'l': bar.l,
                'c': bar.c,
                'v': bar.v
            } for bar in bars]
            print(f"[INFO] Fetched {len(data)} bars for {symbol} {tf}")
            df = pd.DataFrame(data)
            if df.empty:
                print(f"[WARN] No data returned for {symbol} {tf}")
                summary[tf] = {"error": "No data returned"}
                continue
            result = optimize_strategy(df, net_return_target=0.2)
            # Save results
            result_path = os.path.join(RESULTS_DIR, f"{symbol}_{tf}_backtest.json")
            with open(result_path, "w") as f:
                json.dump(result, f, indent=2)
            print(f"[INFO] Saved result to {result_path}")
            summary[tf] = result
        except Exception as e:
            print(f"[ERROR] Exception for {symbol} {tf}: {e}")
            summary[tf] = {"error": str(e)}
    return {"symbol": symbol, "summary": summary}


# CLI entry point for GitHub Actions/static generation
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate static backtest results for dashboard.")
    parser.add_argument('--symbols', nargs='+', default=['BTCUSD', 'CLM'], help='Symbols to backtest')
    parser.add_argument('--timeframes', nargs='+', default=TIMEFRAMES, help='Timeframes to backtest')
    args = parser.parse_args()
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        run_backtest_for_symbol(symbol, args.timeframes)
    print("Static results generated in backend/results/")

@app.get("/api/results/{symbol}")
def get_results(symbol: str):
    # Placeholder: implement logic to fetch results for symbol
    # Return results as JSON or error if not found
    return {"symbol": symbol, "results": "Not implemented"}
