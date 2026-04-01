# VERSION 2 (APM v2) Reference

This document describes what is currently implemented for APM v2 in this repository.

## Scope

- Strategy family: Adaptive Pullback Momentum v2
- Primary timeframe: 10m
- Primary implementation language: Pine Script + Python execution adapters
- Current support state:
  - Pine/template and dashboard dataset support: available
  - Python backtest/paper/live execution support under `--version v2`: wired

## Canonical v2 Pine Strategy

### Main strategy source

- File: `backend/pine_templates/APM v2.0-10m.pine`
- Notes:
  - Declares `@version=6`
  - Uses strategy title `Adaptive Pullback Momentum v2.5`
  - Contains version notes from v2.1 through v2.5 in header comments
  - Implements both long and short conditions, with shorts enabled by default in inputs (`i_shorts=true`, `i_longs=false`)

### Public template copy

- File: `docs/pine_templates/apm_v2_template.pine`
- Purpose:
  - Dashboard/docs-facing Pine template variant for v2
  - Exposes v2 input defaults for user copy/use

## v2 Strategy Characteristics (from Pine implementation)

- Trend structure:
  - EMA 21 / 50 / 200 stack requirements
  - EMA slope direction checks
- Momentum filters:
  - RSI direction (rising/falling)
  - Optional momentum-bars filter
- Volatility and quality gates:
  - ATR floor (% of price)
  - Panic suppression versus ATR baseline
  - Minimum candle-body size in ATR units
  - Volume multiplier gate versus volume SMA
- Session control:
  - ET session window filters in inputs
- Risk model:
  - ATR-based stop and take-profit
  - ATR-activated trailing stop
  - Position sizing based on risk percent of equity
  - Max-bars-in-trade timeout support

## Dashboard and Data Integration

### Dashboard version metadata

- File: `docs/site.js`
- v2 registration:
  - Label: `v2 - 10m Both`
  - Timeframe key: `10m`

### Backtest dataset references

- File: `README.md`
- v2 dataset paths:
  - `docs/data/btcusd/v2_trades.csv`
  - `docs/data/btcusd/v2_trades_12mo.csv`
- Notes:
  - README documents v2 as a dashboard backtest dataset source
  - 12-month export is documented as separate from the main dashboard file

## Python Runtime Support

### New v2 strategy modules

- `backend/strategy_generator/v2_params.py`
  - Adds v2 defaults mapped from `APM v2.0-10m.pine` inputs.
- `backend/strategy_generator/apm_v2.py`
  - Adds v2 latest-bar entry/exit analysis adapters.
  - Uses v2 defaults and supports side-aware analysis.
- `backend/strategy_generator/apm_v2_backtest.py`
  - Adds v2 backtest simulation with long/short handling, ATR stops/targets, trailing logic, and max-bars exit.

### Backtest runner support

- `backend/backtest_backtrader_alpaca.py`
  - `VERSION_MAP` now includes `v2` (`APM v2.0-10m`).
  - `run_backtest(...)` now dispatches `version == "v2"` to `backtest_apm_v2(...)`.

### Realtime paper support

- `backend/paper_trading/realtime_alpaca_paper_trader.py`
  - `--version v2` is accepted.
  - Entry/exit analysis and risk sizing are routed through version-specific strategy params/functions.
  - Existing scheduling, logging, fill sync, and order handling paths are reused for v2.

### Realtime live support

- `backend/live_trading/realtime_alpaca_live_trader.py`
  - `--version v2` is accepted.
  - Entry analysis and risk sizing are routed through version-specific strategy params/functions.
  - Existing live guardrails (`ALLOW_ALPACA_LIVE_TRADING`) and fill sync continue to apply.

## Remaining Enhancements

1. Extend CI/workflow coverage for v2 guideline matrix and optimization reporting.
2. Add v2-specific walk-forward/parameter-tuning automation equivalent to v1 tooling.

## Added v2 Operational Parity Tooling

- `reset_v2_aligned_backtest_paper.py`
  - Regenerates aligned `mode='backtest'` and `mode='paper'` trade rows for v2.
  - Creates a timestamped DB backup before rewrite.
- `backend/paper_trading/verify_v2_parity.py`
  - CI-friendly parity checker for v2 backtest vs paper rows.
- `backend/strategy_generator/validate_v2_config_usage.py`
  - Verifies required v2 param keys and confirms v2 runtime wiring snippets in target files.
- `.github/workflows/validate-v2-config.yml`
  - Adds CI gate for v2 config/runtime usage validation.
- Workflow updates:
  - `.github/workflows/paper-trade.yml` now supports v2 aligned simulation reset and v2 parity checks.
  - `.github/workflows/rerun-backtest-issue.yml` now uses `reset_v2_aligned_backtest_paper.py` for v2 rerun issues.
  - `.github/workflows/rerun-paper-trade-issue.yml` now accepts v2 issue reruns.
