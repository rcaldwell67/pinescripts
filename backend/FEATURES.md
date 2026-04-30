# Backend Features

## Implemented
- Data ingestion from YFinance (`/api/yfinance-bars`)
- News sentiment analysis (`/api/news-sentiment`)
- Active symbols endpoint (`/api/symbols`)
- Health check (`/api/health`)

## Usage
- `/api/yfinance-bars?symbol=AAPL&start=2024-01-01&end=2024-01-31&interval=1d`
- `/api/news-sentiment?symbol=AAPL`

## Next Steps
- Add endpoints for Alpaca data
- Integrate trading strategy engine
- Expand error handling and logging
