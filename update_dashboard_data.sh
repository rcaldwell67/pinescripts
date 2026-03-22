#!/bin/bash
# Automate dashboard data update: run all backtest/export scripts and copy CSVs to dashboard data folders
set -e

# BTCUSD scripts and copy
python3 scripts/BTCUSD/Adaptive\ Pullback\ Momentum\ v1/backtest_apm_v1_5m.py
cp scripts/BTCUSD/Adaptive\ Pullback\ Momentum\ v1/v1_trades.csv docs/data/btcusd/v1_trades.csv

python3 scripts/BTCUSD/Adaptive\ Pullback\ Momentum\ v2/backtest_apm_v2_10m.py
cp scripts/BTCUSD/Adaptive\ Pullback\ Momentum\ v2/v2_trades.csv docs/data/btcusd/v2_trades.csv

python3 scripts/BTCUSD/Adaptive\ Pullback\ Momentum\ v3/backtest_apm_v3_15m.py
cp scripts/BTCUSD/Adaptive\ Pullback\ Momentum\ v3/v3_trades.csv docs/data/btcusd/v3_trades.csv

python3 scripts/BTCUSD/Adaptive\ Pullback\ Momentum\ v4/backtest_apm_v4_30m.py
cp scripts/BTCUSD/Adaptive\ Pullback\ Momentum\ v4/v4_trades.csv docs/data/btcusd/v4_trades.csv

# CLM scripts and copy (add more as needed)
python3 scripts/CLM/Adaptive\ Pullback\ Momentum\ v1/backtest_apm_v1_5m.py
cp scripts/CLM/Adaptive\ Pullback\ Momentum\ v1/v1_trades.csv docs/data/clm/v1_trades.csv

# Add more CLM versions as needed

echo "Dashboard data update complete."
