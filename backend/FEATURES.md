# Backend Features

## Implemented
- Data ingestion from YFinance (`/api/yfinance-bars`)
- News sentiment analysis (`/api/news-sentiment`)
- Active symbols endpoint (`/api/symbols`)
- Health check (`/api/health`)
- Strategy evaluation endpoint (`/api/strategy/evaluate`)
- Backtest endpoint (scaffold) (`/api/backtest`)

## Usage
- `/api/yfinance-bars?symbol=AAPL&start=2024-01-01&end=2024-01-31&interval=1d`
- `/api/news-sentiment?symbol=AAPL`
- POST `/api/strategy/evaluate` with `{ "trades": [...] }`
- POST `/api/backtest` with `{ "symbol": ..., "strategy_params": ..., "start": ..., "end": ... }`

## Next Steps
- Implement full backtesting logic
- Add live trading endpoints
- Expand error handling and logging
