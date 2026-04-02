---EACH TODO IS TO BE WORKED IN NUMERICAL ORDER
---AFTER A TODO IS COMPLETED, ADD TO CHANGELOG.MD AND REMOVE FROM TODO.TXT

1. Convert APM ./backend/pine_templates/APM v1.0-5m.pine into a Python script
    place file in ./backend/backtests folder
    
2. Create backtests based on APM Templates v1-v6 using Backtrader and Alpaca
  a. Create rerun backtesting from the dashboard
  
3. Validate that rerun backtest is working from the dashboard is working for any Symbol

4. Create paper trading
  a. Create rerun paper trading from the dashboard

5. Validate that rerun paper trading from dashboard is working for any Symbol

6. Make sure backtesting and paper trading are 100% for v1-v6

7. Housekeeping, remove all files/folders that are not in use by the project

Note:

- v1 backtesting guideline closure complete: default runtime now passes strategy thresholds for BTC/USD, ETH/USD, CLM, and CRF (validated via report_v1_guidelines.py).
- v1 promoted profile `guideline_closed` now preserves the validated closure state and can be enforced through close_v1_guidelines.py or the matching GitHub Actions workflow.
- v2 backtesting guideline closure complete: default runtime and `guideline_closed` profile now pass strategy thresholds for BTC/USD, ETH/USD, CLM, and CRF (validated via report_v2_guidelines.py --enforce).
- Current v1 paper-trading data has been corrected and made incremental (append new trades each run).
- Current implementation is simulation-based (using strategy backtest logic on fresh OHLCV), not live order placement through Alpaca Paper Trading API yet.
