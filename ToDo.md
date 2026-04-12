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

I've collected the structure and features of the classic dashboard from index.html. Here are the main features available for porting to the React app:

#Symbol selection and management (add, remove, refresh, type filters)

Mode switching (Backtest, Paper Trading, Live Trading)
Balance bar (beginning, ending, total equity, etc.)
Auto-refresh controls
Transaction ticker (latest transactions)
Tabs/cards for dashboard content
All Transactions table with filters (version, timeframe, action, direction, type, page size)
Price chart with range selection and legend
Equity curve chart
Trade outcomes chart
P&L by direction chart
Monthly P&L chart
Year-by-year breakdown chart
Trade log with pagination
Logs panel with filters and search
Version comparison table
Modals: Account Info, Trade Gap Analysis, Daily Transactions, Live Symbol Control, Guideline Audit


The header is now enabled. Here are some common next steps you might consider for your React app:

Add navigation (sidebar or top nav) for multiple pages or views.
Restore or enhance the dashboard features (charts, tables, widgets).
Implement authentication (login/logout).
Add a footer or status bar.
Integrate API/data fetching for live or backtest results.
Improve responsiveness and mobile layout.
Add user settings or theme toggling.
Let me know which feature you’d like to enable next, or if you want suggestions based on your previous dashboard functionality!