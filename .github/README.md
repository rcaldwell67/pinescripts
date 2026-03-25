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