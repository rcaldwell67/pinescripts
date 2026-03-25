# Backend

This folder contains all backend automation scripts for:
- Pine Script generation
- Backtesting with Backtrader
- Paper/live trading with Alpaca API

## Structure
- `generate_pinescript.py` — Generates Pine Script from CUSIP/Symbol input
- `backtest.py` — Runs backtests using Backtrader
- `trade.py` — Handles paper/live trading via Alpaca
- `utils/` — (optional) Shared utility modules

## Setup
1. Create a Python virtual environment:
   ```sh
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   ```
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

## Usage
- Scripts are designed to be run by GitHub Actions or manually for development/testing.

---

See each script for usage details and arguments.

# Development Work To Complete
- create a template for each pinescript strategy version
- ability to add symbols in the dashboard and have backtesting, paper and live trading configured automatically via Github Actions and Workflows
- ability to add values to parameters via the dashboard for items such as Win Rate, Net Return, Max Drawdown; this will allow for fine tuning Pine Script versions from the frontend

# Completed Development Work

# Strategy Guidelines
- Win Rate = 70% or greater
- Net Return = 20% or greater
- Max Drawdown = -4.50 % or less