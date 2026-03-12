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
cp "scripts/BTCUSD/Adaptive Pullback Momentum v1/apm_v1_trades_btcusd_15m.csv" docs/data/v1_trades.csv
cp "scripts/BTCUSD/Adaptive Pullback Momentum v2/apm_v2_trades_btcusd_30m.csv" docs/data/v2_trades.csv
cp "scripts/BTCUSD/Adaptive Pullback Momentum v3/apm_v3_trades_btcusd_1h.csv"  docs/data/v3_trades.csv
cp "scripts/BTCUSD/Adaptive Pullback Momentum v4/apm_v4_trades_btcusd_1d.csv"  docs/data/v4_trades.csv
```
