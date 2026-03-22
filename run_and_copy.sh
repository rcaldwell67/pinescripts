#!/bin/bash
# Run backtest and copy results for dashboard static hosting
set -e

# Run backtest for default symbols (edit as needed)
.venv/bin/python backend/main.py --symbols BTCUSD CLM

# Copy results to dashboard public/data
cp -v backend/results/*.json dashboard/public/data/
echo "Backtest and copy complete."
