# Tradingview
## Important: About the `localbackup` Folder

This repository contains a `localbackup` directory, which is a backup copy of the main project structure. **Do not edit files in `localbackup` unless you are intentionally restoring or comparing versions.** All development should occur in the main project directories. If you are unsure about the purpose of a file or folder, consult the project maintainer before making changes.


## APM Dashboard (GitHub Pages)

Live dashboard for the Adaptive Pullback Momentum strategy suite â€” equity curves, trade logs, performance metrics, and version comparisons across the BTC-USD and CLM strategy sets from 5m through 1D.

**âžœ [View Dashboard](https://rcaldwell67.github.io/pinescripts/)**

### Setup

1. Push the `docs/` folder to GitHub
2. Go to **Settings â†’ Pages** in the repository
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

## Trading System Documentation

## React Trading Monitor (Crypto + ETFs)

A new React dashboard scaffold is available in `frontend-react/` and reads a snapshot JSON generated from `tradingcopilot.db`.

### Generate snapshot data

```bash
python backend/data/export_dashboard_snapshot.py
```

This writes:

- `docs/data/dashboard_snapshot.json`
- `frontend-react/public/data/dashboard_snapshot.json`

### Run the React monitor

```bash
npm --prefix frontend-react install
npm --prefix frontend-react run dev
```

### Build the React monitor

```bash
npm --prefix frontend-react run build
```

You can also use root-level scripts:

- `npm run dashboard:export`
- `npm run dashboard:dev`
- `npm run dashboard:build`

This repository implements an Adaptive Pullback Momentum (APM) trading system with versioned strategy logic, shared risk controls, and separate backtest, paper, and live execution paths.

### Design goals

- Target positive expectancy with controlled drawdown instead of maximizing trade count.
- Enforce regime filtering before entries (trend structure, momentum, volatility, liquidity).
- Keep paper and live execution auditable through explicit event logs.
- Validate strategy behavior with repeatable scripts and profile-scoped runtime configs.

### System architecture

- Strategy layer

  - v1 through v6 signal adapters live under backend/strategy_generator.
  - v1 is the baseline evaluator; v2-v6 reuse the shared entry/exit evaluation framework with version-specific defaults and overrides.
  - Runtime overrides are loaded from backend/strategy_generator/configs/v1_runtime.json through v6_runtime.json.

- Risk and trade management layer

  - ATR-based stop, target, and trailing logic.
  - Percent-risk position sizing with symbol-level override support.
  - Session and volatility gating to avoid low-quality setups.

- Execution layer

  - Backtest engine: backend/backtest_backtrader_alpaca.py.
  - Realtime paper runner: backend/paper_trading/realtime_alpaca_paper_trader.py.
  - Realtime live runner: backend/live_trading/realtime_alpaca_live_trader.py.

- Observability layer

  - Trade records: trades table in docs/data/tradingcopilot.db.
  - Realtime decision log: realtime_paper_log table.
  - Broker fill and order events: paper_fill_events and paper_order_events tables.
  - Missed-window audit: backend/paper_trading/validate_missed_opportunities.py.
  - Scheduler-health audit: backend/paper_trading/validate_scheduler_health.py.
  - Dashboard rendering: docs/index.html + docs/site.js.

### Entry model (v1-v6 shared evaluator)

Entries are stage-gated. A bar must pass all enabled gates in sequence:

- EMA stack alignment

  - Long path: ema21 > ema50 > ema200
  - Short path: ema21 < ema50 < ema200

- EMA slope confirmation
- ADX threshold (and optional ADX slope)
- Optional DI spread check
- RSI direction and RSI range checks
- Momentum check against lookback bars
- Pullback and break confirmation
- Volume threshold versus volume SMA
- ATR floor and panic suppression checks
- Optional session-hours gating

Near misses are logged when a bar passes some stages but fails before entry.

### Version behavior

- v1

  - Baseline side-aware evaluator used for long/short regime gating.
  - Tuned with symbol-specific overrides for BTC/USD, ETH/USD, CLM, and CRF.

- v2-v6

  - Use version-specific defaults and runtime overrides from v2-v6 runtime config files.
  - Reuse the shared evaluator path while preserving per-version risk and entry parameterization.

### Data source separation (important)

The trades table now includes a source column:

- source = simulation

  - Generated by aligned reset scripts for deterministic parity/backfill.

- source = realtime

  - Generated from broker-synced realtime execution paths.

Dashboard behavior uses source-aware filtering:

- Live view: broker-only rows (`source='realtime'`).
- Paper view: prefer broker rows when present, otherwise fall back to simulation/null-source rows.

### Aligned reset workflow

Use the unified aligned reset script to regenerate deterministic parity inputs
across strategy versions:

- `python reset_aligned_backtest_paper.py --all-versions`
- `python reset_aligned_backtest_paper.py --version v3 --symbol BTC/USD`

Legacy entrypoints are preserved as wrappers:

- `reset_v1_aligned_backtest_paper.py`
- `reset_v2_aligned_backtest_paper.py`

### Dashboard data integrity check

Run this utility to detect missing symbol/version coverage and summary-vs-trade drift:

- `python backend/data/validate_dashboard_data_integrity.py`

### Backtest rerun validation

Run this utility to validate the two issue-driven rerun backtest paths against a temporary DB copy:

- `python backend/data/validate_rerun_backtests.py`

By default it validates the aligned-reset branch and the direct-backtest branch on `BTC/USDT` and `CLM`, then runs the dashboard integrity check on the temporary DB so the workspace stays clean.

### Paper rerun validation

Run this utility to validate the issue-driven realtime paper rerun path against a temporary DB copy and a fake paper broker:

  

It validates actual versioned paper analysis/exit dispatch on local sample data, then dry-runs representative crypto and non-crypto paper reruns through the realtime runner without placing broker orders.

### Profile and guideline workflow

Guideline-closed profiles exist for both versions and are intended as promoted runtime states:

- v1 closure script: backend/strategy_generator/close_v1_guidelines.py
- v2 closure script: backend/strategy_generator/close_v2_guidelines.py

Guideline reports and CI workflows enforce threshold compliance before profile promotion.

### Realtime health and missed-opportunity handling

- Scheduler gaps are logged as schedule_miss in realtime_paper_log.
- Optional catch-up scanning can replay missed windows in log-only mode and record:

  - missed_opportunity
  - missed_opportunity_blocked

- This is observability logic only; no late orders are submitted during catch-up replay.

### Operating principles

- Treat backtest, paper, and live as separate datasets with explicit provenance.
- Prefer reproducible profile closures over ad-hoc parameter edits.
- Investigate persistent near-miss clusters by failed stage (for example, bullish_stack or bearish_stack) before changing thresholds.
- Preserve risk controls first; tune entry gates second.

## TradingStrategy Constraints & Adjustments
- To ensure you hit those specific targets during your backtest, keep these nuances in mind:

## Max Drawdown (< 4.5%)
- Controlled by Position Sizing. By only committing 20% of your wallet to a single trade, even a 10% flash crash on BTC only results in a 2% total account drawdown.

## Win Rate (> 65%)
- Achieved by the Trend Filter. RSI buy signals are notoriously fake during bear markets; only buying during a macro uptrend (Price > EMA 200) filters out the "losing" oversold signals.

## Net Return (> 15%)
- Dependent on Volatility. This strategy relies on "compounding" small wins. In a YTD context, BTC usually provides enough RSI oscillations to hit this return within 4-5 months.