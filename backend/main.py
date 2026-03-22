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
load_dotenv()

app = FastAPI()

# Supported timeframes
TIMEFRAMES = ["5m", "10m", "15m", "30m", "1h", "1d"]

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER_BASE_URL = os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets")
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
        base_url=ALPACA_PAPER_BASE_URL
    )

def run_backtest(df: pd.DataFrame) -> dict:
    # Placeholder: simple moving average crossover strategy
    df['sma_fast'] = df['c'].rolling(window=10).mean()
    df['sma_slow'] = df['c'].rolling(window=30).mean()
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
        "returns": returns
    }

@app.post("/api/backtest")
def backtest_symbol(req: BacktestRequest):
    api = get_alpaca_api()
    summary = {}
    for tf in req.timeframes:
        try:
            bars = api.get_bars(req.symbol, tf, limit=500)
            data = [{
                't': bar.t,
                'o': bar.o,
                'h': bar.h,
                'l': bar.l,
                'c': bar.c,
                'v': bar.v
            } for bar in bars]
            df = pd.DataFrame(data)
            if df.empty:
                summary[tf] = {"error": "No data returned"}
                continue
            result = run_backtest(df)
            # Save results
            result_path = os.path.join(RESULTS_DIR, f"{req.symbol}_{tf}_backtest.json")
            with open(result_path, "w") as f:
                json.dump(result, f, indent=2)
            summary[tf] = result
        except Exception as e:
            summary[tf] = {"error": str(e)}
    return {"symbol": req.symbol, "summary": summary}

@app.get("/api/results/{symbol}")
def get_results(symbol: str):
    # Placeholder: implement logic to fetch results for symbol
    # Return results as JSON or error if not found
    return {"symbol": symbol, "results": "Not implemented"}
