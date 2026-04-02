# Tradingview

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

This repository implements an Adaptive Pullback Momentum (APM) trading system with versioned strategy logic, shared risk controls, and separate backtest, paper, and live execution paths.

### Design goals

- Target positive expectancy with controlled drawdown instead of maximizing trade count.
- Enforce regime filtering before entries (trend structure, momentum, volatility, liquidity).
- Keep paper and live execution auditable through explicit event logs.
- Validate strategy behavior with repeatable scripts and profile-scoped runtime configs.

### System architecture

- Strategy layer

  - v1 and v2 signal engines live under backend/strategy_generator.
  - v2 currently reuses the shared entry/exit evaluation framework used by v1, with version-specific defaults and overrides.
  - Per-symbol and per-profile runtime overrides are loaded from backend/strategy_generator/configs/v1_runtime.json and backend/strategy_generator/configs/v2_runtime.json.

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
  - Dashboard rendering: docs/index.html + docs/site.js.

### Entry model (v1/v2 shared evaluator)

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

  - Supports long/short side-aware evaluation depending on symbol and execution mode.
  - Tuned with symbol-specific overrides for BTC/USD, ETH/USD, CLM, and CRF.

- v2

  - Uses v2 defaults and overrides from v2 runtime config.
  - Current runtime has enable_longs = false and enable_shorts = true by default for configured symbols.

### Data source separation (important)

The trades table now includes a source column:

- source = simulation

  - Generated by aligned reset scripts for deterministic parity/backfill.

- source = realtime

  - Generated from broker-synced realtime execution paths.

Dashboard behavior is set to show broker-only rows for paper and live views.

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
