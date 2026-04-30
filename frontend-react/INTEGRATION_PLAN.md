# Frontend Integration Plan

## 1. API Service Layer
- Centralize all backend API calls in `src/api.js`.
- Use environment variable `REACT_APP_API_BASE` for backend URL.

## 2. Strategy Management UI
- List available symbols and strategies.
- Allow user to select symbol, strategy version, and parameters.
- Integrate with `/api/strategy/evaluate` and `/api/backtest`.

## 3. Backtesting UI
- Form to run backtests (symbol, version, timespan, params).
- Display backtest results and metrics (win rate, net return, max drawdown).
- Visualize trades and performance over time.

## 4. Live Trading UI
- Form to place live trades (symbol, qty, side).
- Display current positions and recent orders.
- Integrate with `/api/live-trade`, `/api/live-positions`, `/api/live-orders`.

## 5. News & Sentiment UI
- Show news headlines and sentiment for selected symbol.
- Integrate with `/api/news-sentiment`.

## 6. Error Handling & Loading States
- Show user-friendly errors and loading indicators for all API calls.

## 7. Next Steps
- Implement and test each UI component.
- Connect UI to API service layer.
- Iterate based on user feedback.
