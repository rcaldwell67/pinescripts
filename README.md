# Tradingview

## APM Dashboard (GitHub Pages)

Live dashboard for the Adaptive Pullback Momentum strategy suite — equity curves, trade logs, performance metrics, and version comparisons across the BTC-USD and CLM strategy sets from 5m through 1D.

**➜ [View Dashboard](https://rcaldwell67.github.io/pinescripts/)**

### Setup

1. Push the `docs/` folder to GitHub
2. Go to **Settings → Pages** in the repository
3. Set **Source** to `Deploy from a branch`, branch `main` (or `dev`), folder `/docs`
4. The site will be live at `https://rcaldwell67.github.io/pinescripts/`

### Updating data

The dashboard backtest feeds live in `docs/data/btcusd/` and `docs/data/clm/`.

For BTC-USD, update the dashboard by running the backtest/export scripts and copying the canonical trade CSVs into `docs/data/btcusd/`:

```bash
python3 "scripts/BTCUSD/Adaptive Pullback Momentum v1/backtest_apm_v1_5m.py"
cp "scripts/BTCUSD/Adaptive Pullback Momentum v2/apm_v2_trades_btcusd_10m.csv"     docs/data/btcusd/v2_trades.csv
cp "scripts/BTCUSD/Adaptive Pullback Momentum v3/apm_v3_trades_btcusd_15m.csv"     docs/data/btcusd/v3_trades.csv
cp "scripts/BTCUSD/Adaptive Pullback Momentum v4/apm_v4_trades_btcusd_30m.csv"     docs/data/btcusd/v4_trades.csv
```

For BTC-USD v1 and v2, the dashboard backtesting datasets are `docs/data/btcusd/v1_trades.csv` and `docs/data/btcusd/v2_trades.csv`. Their 12-month backtests are exported separately as `docs/data/btcusd/v1_trades_12mo.csv` and `docs/data/btcusd/v2_trades_12mo.csv` and should not overwrite the dashboard files.

For BTC-USD v1, use the backtest scripts to write the dashboard-format CSVs because the raw strategy CSVs use `entry`/`exit` while the dashboard expects `entry_price`/`exit_price`.

For CLM, the dashboard backtest files are `docs/data/clm/v1_trades.csv` through `docs/data/clm/v6_trades.csv`.

Current CLM sync behavior:

- `scripts/CLM/Adaptive Pullback Momentum v4/backtest_apm_v4_30m_v46.py` writes its generated exports into `scripts/CLM/Adaptive Pullback Momentum v4/outputs/` and rewrites `docs/data/clm/v4_trades.csv` in dashboard format automatically.
- `scripts/CLM/Adaptive Pullback Momentum v5/backtest_apm_v5_1h.py` writes `scripts/CLM/Adaptive Pullback Momentum v5/outputs/apm_v5_trades_clm_1h.csv`, writes its alert log into the same `outputs/` folder, and syncs `docs/data/clm/v5_trades.csv` automatically.
- `scripts/CLM/Adaptive Pullback Momentum v6/backtest_apm_v6_1d.py` writes `scripts/CLM/Adaptive Pullback Momentum v6/outputs/apm_v6_trades_clm_1d.csv`, writes its alert log into the same `outputs/` folder, and syncs `docs/data/clm/v6_trades.csv` automatically.

The root-level exports are not always the dashboard source of truth. In particular, `apm_v4_trades_clm_30m.csv` is not the canonical dashboard file; the dashboard uses the remapped output written by `backtest_apm_v4_30m_v46.py` to `docs/data/clm/v4_trades.csv`.

To verify the CLM dashboard feeds against the canonical generated outputs, run:

```bash
python3 scripts/CLM/validate_dashboard_sync.py
```

Use `python3 scripts/CLM/validate_dashboard_sync.py --sync` if you want the validator to refresh `docs/data/clm/v4_trades.csv` through `v6_trades.csv` from the latest generated outputs before comparing them.

The dashboard exposes backtest-only selectors for BTC-USD v1 and v2 so you can switch between the main backtest feeds and the separate 12-month exports without affecting paper or live views.
