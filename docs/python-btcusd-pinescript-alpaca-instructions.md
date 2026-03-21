# Instructions: Python Script for BTCUSD & CLM Trading Using Pine Script Reference and Alpaca Data

## Objective
Create a Python script that:
- Uses a TradingView Pine Script strategy as a reference for trading logic.
- Fetches historical and live BTCUSD and CLM data from Alpaca Markets.
- Backtests the strategy to target a net return of +20%.
- Supports paper trading on Alpaca for live signal validation.

## Steps

### 1. Reference Pine Script
- Select a Pine Script strategy (e.g., from `scripts/BTCUSD/Adaptive Pullback Momentum v6/Adaptive Pullback Momentum v6.0.pine` or `scripts/CLM/Adaptive Pullback Momentum v6/Adaptive Pullback Momentum v6.0.pine`).
- Translate the core trading logic (entry/exit, indicators, risk management) into Python for both BTCUSD and CLM.

### 2. Alpaca API Setup
- Register for Alpaca Markets and obtain API keys.
- Install the `alpaca-trade-api` Python package.
- Authenticate and connect to Alpaca for both data and paper trading endpoints.

### 3. Data Acquisition
- Download historical BTCUSD and CLM price data (1h or 1d candles recommended) for backtesting.
- Implement a data loader to fetch and preprocess data for the backtest.

### 4. Strategy Implementation
- Reproduce the Pine Script logic in Python (use `pandas` for data manipulation).
- Ensure all indicators and conditions match the Pine Script as closely as possible for both BTCUSD and CLM.

### 5. Backtesting
- Simulate trades using historical data for both BTCUSD and CLM.
- Track portfolio value, drawdown, and net return.
- Aim for a net return of +20% or higher.
- Output a performance report (returns, win rate, max drawdown, etc.) for each symbol.

### 6. Paper Trading
- Connect to Alpaca's paper trading API.
- Place simulated orders based on live signals from the Python strategy for both BTCUSD and CLM.
- Log all trades and monitor real-time performance.

### 7. Optimization (Optional)
- Tune strategy parameters to improve performance if +20% net return is not achieved.
- Use grid search or other optimization techniques.

### 8. Reporting
- Save backtest and paper trading logs to CSV or JSON.
- Generate summary plots (equity curve, drawdown, etc.) for both BTCUSD and CLM.

## Recommended Libraries
- `alpaca-trade-api`
- `pandas`, `numpy`
- `matplotlib` or `plotly` (for visualization)
- `ta` (for technical indicators, if needed)

## Deliverables
- Python script(s) implementing the above for BTCUSD and CLM.
- README with setup and usage instructions.
- Example configuration for API keys and parameters.

---

**Note:**
- Ensure all API keys are kept secure and not hard-coded in public files.
- Validate results with both backtesting and paper trading before considering the strategy successful.
