# Backend Features

## Implemented
- Data ingestion from YFinance (`/api/yfinance-bars`)
- News sentiment analysis (`/api/news-sentiment`)
- Active symbols endpoint (`/api/symbols`)
- Health check (`/api/health`)
- Strategy evaluation endpoint (`/api/strategy/evaluate`)
- Backtest endpoint (`/api/backtest`)
- Live trading endpoint (`/api/live-trade`)
- Live positions endpoint (`/api/live-positions`)
- Live orders endpoint (`/api/live-orders`)

## Usage
- `/api/yfinance-bars?symbol=AAPL&start=2024-01-01&end=2024-01-31&interval=1d`
- `/api/news-sentiment?symbol=AAPL`
- POST `/api/strategy/evaluate` with `{ "trades": [...] }`
- POST `/api/backtest` with `{ "symbol": ..., "version": ..., "timespan": ... }`
- POST `/api/live-trade` with `{ "symbol": ..., "qty": ..., "side": ... }`
- GET `/api/live-positions`
- GET `/api/live-orders`

## Next Steps
- Expand error handling and logging
- Integrate frontend with backend APIs
- Add advanced strategy and risk management features
