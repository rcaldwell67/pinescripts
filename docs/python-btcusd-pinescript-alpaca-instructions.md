# Implementation Guide: Backend for Dashboard Trading System

> **Reference:** See `.github/copilot-python-btcusd-clm-instructions.md` for high-level requirements and agent workflow. This file provides detailed implementation steps for the backend and dashboard integration.


## Objective
Implement a backend service that:
- Accepts symbol input from the dashboard (e.g., BTCUSD, CLM, or any new symbol).
- Fetches historical and live data from Alpaca for six timeframes: 5m, 10m, 15m, 30m, 1h, 1d.
- Backtests Pine Script-derived strategies for each symbol and timeframe, targeting a net return of +20%.
- Supports paper and live trading via Alpaca.
- Returns results and logs to the dashboard for visualization and monitoring.


## Implementation Steps

### 1. API Endpoint for Symbol Input
- Expose a REST API endpoint (e.g., `/api/backtest`) to accept a symbol and timeframe from the dashboard.
- Validate input and trigger the backtesting workflow for the requested symbol and all six timeframes (5m, 10m, 15m, 30m, 1h, 1d).

### 2. Pine Script Strategy Translation
- For each symbol, select the latest Pine Script strategy from the `scripts/` directory.
- Translate entry/exit logic, indicators, and risk management to Python using `pandas` and optionally `ta`.
- Ensure parity with the Pine Script logic for each timeframe.

### 3. Alpaca API Integration
- Use `alpaca-trade-api` to fetch historical OHLCV data for the symbol and all required timeframes.
- Authenticate using API keys (read from environment variables or a secure config file).
- For paper/live trading, use the appropriate Alpaca endpoint.

### 4. Backtesting Engine
- Simulate trades for each symbol and timeframe using the translated strategy logic.
- Track performance metrics: net return, drawdown, win rate, equity curve.
- Ensure the strategy targets a net return of +20% or higher in backtesting.
- Store results and logs in CSV/JSON for dashboard consumption.

### 5. Paper and Live Trading
- For paper trading, place simulated orders via Alpaca's paper trading API.
- For live trading, use the live trading endpoint (ensure proper safeguards and logging).
- Log all trades and monitor real-time performance.

### 6. Dashboard Integration
- Save all results, logs, and summary statistics to files accessible by the dashboard (e.g., in a `public/data/` directory).
- Update the dashboard automatically as new results are generated.
- Support filtering and visualization by symbol, timeframe, and trading mode (backtest, paper, live).

### 7. Reporting and Visualization
- Generate summary plots (price, indicators, equity curve, drawdown) using `matplotlib` or `plotly`.
- Output performance reports for each symbol and timeframe.
- Ensure all assets are static and compatible with GitHub Pages deployment.

### 8. Security and Configuration
- Store API keys securely (never hard-code in public files).
- Provide an example config file and update the README with setup instructions.

---

For requirements and agent workflow, see `.github/copilot-python-btcusd-clm-instructions.md`.

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
