# Backend for Trading Dashboard (FastAPI)

This backend provides REST API endpoints for symbol input, backtesting, and trading using Alpaca data. Results are output as CSV/JSON for a static dashboard (e.g., hosted on GitHub Pages).

## Features
- Accepts symbol and timeframe input from dashboard
- Backtests Pine Script-derived strategies for 5m, 10m, 15m, 30m, 1h, 1d
- Integrates with Alpaca for historical and live data
- Supports paper and live trading
- Outputs results/logs for dashboard visualization

## Setup
1. Clone the repository and navigate to `backend/`
2. Create a `.env` file from `.env.example` and add your Alpaca API keys
3. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Run the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```

## API Endpoints
- `POST /api/backtest` — Trigger backtest for a symbol and all timeframes
- `GET /api/results/{symbol}` — Get backtest/paper/live results for a symbol

## Notes
- All output files (CSV/JSON) are saved in `backend/results/` for dashboard access
- Designed for compatibility with static dashboards hosted on GitHub Pages

See the main project documentation for full implementation details.
