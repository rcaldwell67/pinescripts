# Tradingview

## APM Dashboard (GitHub Pages)

Live dashboard for the Adaptive Pullback Momentum strategy suite — equity curves, trade logs, performance metrics, and version comparisons across all four timeframes (15m, 30m, 1h, 1D).

**➜ [View Dashboard](https://rcaldwell67.github.io/pinescripts/)**

### Setup

1. Push the `docs/` folder to GitHub
2. Go to **Settings → Pages** in the repository
3. Set **Source** to `Deploy from a branch`, branch `main` (or `dev`), folder `/docs`
4. The site will be live at `https://rcaldwell67.github.io/pinescripts/`

### Updating data

When new backtests produce updated CSV files, copy them to `docs/data/`:

```bash
cp "scripts/BTCUSD/Adaptive Pullback Momentum v1/apm_v1_ytd_trades_btcusd_5m.csv"  docs/data/btcusd/v1_trades.csv
cp "scripts/BTCUSD/Adaptive Pullback Momentum v2/apm_v2_trades_btcusd_10m.csv"     docs/data/btcusd/v2_trades.csv
cp "scripts/BTCUSD/Adaptive Pullback Momentum v3/apm_v3_trades_btcusd_15m.csv"     docs/data/btcusd/v3_trades.csv
cp "scripts/BTCUSD/Adaptive Pullback Momentum v4/apm_v4_trades_btcusd_30m.csv"     docs/data/btcusd/v4_trades.csv
```

For BTC-USD v2, the dashboard backtesting dataset is `docs/data/btcusd/v2_trades.csv`. The 12-month backtest is exported separately as `docs/data/btcusd/v2_trades_12mo.csv` and should not overwrite the dashboard file.

The dashboard exposes a backtest-only V2 dataset selector so you can switch between the main backtest feed and the separate 12-month export without affecting paper or live views.
