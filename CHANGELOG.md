# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Standardized `current_equity` persistence and dashboard display across backtest, paper, and live paths.
  - Added `current_equity` column to `backtest_results`, `paper_trading_results`, and `live_trading_results` in DB bootstrap DDL.
  - Added runtime schema hardening (`ALTER TABLE ... ADD COLUMN current_equity`) in summary writers so existing DBs are upgraded automatically.
  - Updated backtest and paper simulation summary metrics to include `current_equity` (aliased to final equity for closed-run datasets).
  - Updated realtime paper/live summary writes to persist `current_equity` both in metrics JSON and in the table column.
  - Updated dashboard cards to show `Current Equity` explicitly, preferring account `current_balance` for paper/live when available and falling back to summary/trade equity.
  - Updated account modal panels to show a `Current Equity Snapshot` row with value, source mode, and human-readable timestamp.
  - Added freshness/staleness age badges for equity snapshots in both the `Current Equity` card subtitle and account modal snapshot row.

- Extended `guideline_closed` profile to cover ETH pairs (ETH/BTC, ETH/USDC, ETH/USDT) across v1–v6 via targeted parameter tuning.
  - v1 ETH/BTC: 67.21% WR, 19.07% net return, 3.15% max DD — all constraints met.
  - v1 ETH/USDC: 68.82% WR, 100.93% net return, 4.49% max DD — all constraints met.
  - v1 ETH/USDT: 66.13% WR, 17.26% net return, 3.54% max DD — all constraints met.
  - v2–v6 ETH pairs tuned with `tune_v2_profile.py` / `tune_v3_v6_profile.py`; best-available candidate applied via `--apply-best-available`.
  - Per-symbol `guideline_closed` overrides written to `v1_runtime.json` through `v6_runtime.json`.
  - Tuning result snapshots written to `docs/data/v{1..6}_profile_tuning_result_eth{btc,usdc,usdt}_guideline_retry.json`.

- Housekeeping: removed 35+ obsolete scripts, data files, and database snapshots.
  - Root: removed one-off debug scripts (`check_yesterday*.py`, `diagnostics_summary.py`, `scheduler_gap_analysis.py`, `missed_opportunities_report.py`), Playwright diagnostics, CSV trade exports, shell rename helper, paper reset shims (`reset_paper_data.py`, `reset_paper_tmp.py`, `reset_v1/v2_aligned_backtest_paper.py`), and other single-use utilities.
  - `backend/data/`: removed bootstrap CSV files, temp data files, and migration script superseded by current DDL.
  - `backend/strategy_generator/`: removed v1-only analysis scripts (`run_apm_v1_backtest.py`, `save_apm_v1_summary_to_db.py`, `summarize_apm_v1_results.py`), walkforward optimizer, parameter extractor, and filter-impact analyzer; removed orphaned `v1_optimized_walkforward_smoketest.json` config.
  - `docs/`: removed `index_head_snapshot.html` one-off capture.
  - `docs/data/`: removed 19 old pre-align DB snapshots (retaining last 3), temp/scratch DBs, paper-fill temp DB, diagnostic JSONL log files, and stale guideline report variants.
  - Removed empty `backend/backtests/` directory.

- Added `backend/data/validate_rerun_backtests.py` to validate representative backtest rerun paths on a temporary DB copy.
  - Covers both issue-workflow branches: aligned reset reruns (default `v2`) and direct backtest reruns (default `v6`).
  - Defaults to validating both `BTC/USDT` and `CLM` so crypto and non-crypto rerun paths are checked together.
  - Reuses `backend/data/validate_dashboard_data_integrity.py` against the temp DB to confirm summary/trade coherence without dirtying the workspace.
- Added `.github/workflows/validate-rerun-backtests.yml` to run the rerun validator in GitHub Actions on demand and on relevant `main` branch changes.
- Removed `backend/paper_trading/validate_rerun_paper_trading.py` (deprecated, depended on missing sample CSV logic, no longer functional or referenced).
  - Validates actual versioned entry/exit dispatch and order parameter calculation on local sample data.
  - Dry-runs representative crypto (`BTC/USDT` v2 long) and non-crypto (`CLM` v6 short) paper reruns without placing broker orders.
  - Confirms summary writes, realtime fill ingestion, and paper trade persistence with `source='realtime'`.
- Added `.github/workflows/validate-rerun-paper-trading.yml` to run the paper rerun validator in GitHub Actions on demand and on relevant `main` branch changes.

- Generalized remaining v1/v2 utility workflows to v1-v6 coverage.
  - Updated `export_trades_to_json.py` and `backend/data/import_trades_to_db.py` default trade-file mappings to iterate versions `v1` through `v6`.
  - Updated `reset_paper_data.py` and `reset_paper_tmp.py` force-reset loops to execute all supported versions (`v1`-`v6`) per symbol.
  - Updated `verify_fix.py` to run backtest verification across `v1`-`v6` instead of only `v1`.
  - Updated dashboard dataset-switcher version wiring in `docs/site.js` to use shared version keys (`v1`-`v6`) instead of v1/v2-only hardcoded listeners/checks.
- Added unified aligned reset utility `reset_aligned_backtest_paper.py`.
  - New script supports `--version` (repeatable), `--all-versions`, and `--symbol` for deterministic aligned backtest/paper regeneration across `v1`-`v6`.
  - Converted `reset_v1_aligned_backtest_paper.py` and `reset_v2_aligned_backtest_paper.py` into compatibility wrappers that forward to the new unified entrypoint.
  - Documented unified usage in `README.md` under an "Aligned reset workflow" section.

- Extended strategy version support to v3-v6 across backtest and realtime execution paths.
  - Added version adapters `backend/strategy_generator/apm_v3.py` through `backend/strategy_generator/apm_v6.py`.
  - Added parameter loaders `backend/strategy_generator/v3_params.py` through `backend/strategy_generator/v6_params.py` with runtime/profile/symbol override merge behavior.
  - Added runtime config stubs `backend/strategy_generator/configs/v3_runtime.json` through `backend/strategy_generator/configs/v6_runtime.json`.
  - Extended `backend/backtest_backtrader_alpaca.py` `VERSION_MAP` and dispatch to run v3-v6.
  - Extended realtime paper/live runners to accept v3-v6 and route entry/exit analysis via version-aware dispatch.
  - Updated dashboard filters in `docs/site.js` so backtest equity and transaction rollups include v1-v6 (replacing previous v1/v2-only filters).
- Extended operational GitHub workflows to process v1-v6 consistently.
  - `paper-trade.yml`, `alpaca-paper-sync.yml`, and `live-trade.yml` now accept `version=all` and validate/loop versions across v1-v6.
  - `add-symbol.yml` and `add-symbol-from-issue.yml` now run backtest and paper simulation for all versions v1-v6 when onboarding a symbol.
  - Issue-triggered rerun workflows now validate parsed versions against v1-v6 before execution.
  - `backtrader-backtest.yml` now runs a deterministic local-data smoke validator across v1-v6 instead of scanning arbitrary `backtest_*.py` files.
  - Added `validate-paper-versions.yml` to verify v1-v6 paper simulation writes against a temporary SQLite copy during CI.
  - Added `validate-live-versions.yml` to verify v1-v6 live-side analysis and dry order generation without broker submission during CI.
- Added `backend/strategy_generator/validate_all_versions_smoke.py` to validate v1-v6 backtest plus realtime paper/live analysis dispatch on local sample market data.
- Added `backend/live_trading/validate_live_versions_dry.py` to validate v1-v6 live analysis, portfolio gating, and bracket order parameter generation on local sample data.
- Fixed paper simulation trade-direction persistence for multi-direction versions.
  - `backend/paper_trading/paper_trade_backtrader_alpaca.py` now stores `direction` from each trade row (`side`) instead of hardcoding `short`, enabling correct v4-v6 long/both-mode paper rows.
- Implemented a portfolio-level trade gate and risk scaler in `backend/strategy_generator/portfolio_system.py` and wired it into both realtime runners.
  - New `evaluate_trade(...)` regime check enforces stack alignment quality, ADX floor, ATR floor, and liquidity ratio before order submission.
  - Portfolio thresholds are now config-driven through `portfolio` settings in v1/v2 params (supports profile and symbol overrides via existing runtime merge flow).
  - Paper runner (`backend/paper_trading/realtime_alpaca_paper_trader.py`) now logs `portfolio_filter` when a strategy signal is blocked by portfolio rules.
  - Live runner (`backend/live_trading/realtime_alpaca_live_trader.py`) now applies the same portfolio filter path for consistency.
  - Order sizing in both runners now supports portfolio risk scaling via `risk_multiplier`.
- Added `source` column to the `trades` table (values: `'simulation'`, `'realtime'`, or NULL for backtest rows).
  - `reset_v1_aligned_backtest_paper.py` and `reset_v2_aligned_backtest_paper.py` now tag paper-mode rows with `source='simulation'`.
  - `realtime_alpaca_paper_trader.py` now tags broker-filled paper-mode rows with `source='realtime'` and ensures the column exists via `_ensure_source_column()` on startup.
  - Migration: existing 31 paper rows in `tradingcopilot.db` backfilled to `source='simulation'`.
  - Dashboard: transactions table now shows an amber warning banner when all paper trades are simulation-sourced; shows a `sim` badge per row when simulation and realtime rows are mixed.
- Closed v2 backtesting guideline gap by promoting validated BTCUSD and ETHUSD overrides into `backend/strategy_generator/configs/v2_runtime.json`; default v2 now passes all guideline thresholds across BTC/USD, ETH/USD, CLM, and CRF.
- Added standalone v2 guideline matrix report at `backend/strategy_generator/report_v2_guidelines.py` with JSON output and enforced failure mode.
- Expanded `backend/strategy_generator/tune_v2_profile.py` with broader search coverage, stronger win-rate-first ranking, and profile-scoped apply support.
- Added `backend/strategy_generator/close_v2_guidelines.py` to run the full v2 closure loop: retune, validate, and enforce.
- Updated `.github/workflows/v2-guideline-matrix.yml` to default scheduled and manual runs to the promoted `guideline_closed` profile.
- Added `.github/workflows/close-v2-guidelines.yml` for manual execution of the full v2 closure loop in GitHub Actions.
- Added promoted v1 `guideline_closed` profile plus `backend/strategy_generator/close_v1_guidelines.py` and `.github/workflows/close-v1-guidelines.yml` so v1 and v2 now share the same closure workflow pattern.
- Updated `.github/workflows/v1-guideline-matrix.yml` to default scheduled and manual matrix runs to v1 profile `guideline_closed`, with custom profile override support.
- Added v2 runtime parameter source at `backend/strategy_generator/v2_params.py` based on `APM v2.0-10m` defaults.
- Added v2 strategy adapter at `backend/strategy_generator/apm_v2.py` with side-aware latest-bar entry/exit analysis wiring.
- Added v2 backtest engine at `backend/strategy_generator/apm_v2_backtest.py` with long/short simulation, ATR-based SL/TP, trailing stop, and max-bars exit handling.
- Extended `backend/backtest_backtrader_alpaca.py` to support `--version v2` dispatch and `VERSION_MAP` registration.
- Extended realtime paper runner `backend/paper_trading/realtime_alpaca_paper_trader.py` to support `--version v2` through version-aware analysis and risk-parameter routing.
- Extended realtime live runner `backend/live_trading/realtime_alpaca_live_trader.py` to support `--version v2` through version-aware analysis and risk-parameter routing.
- Added aligned v2 reset utility `reset_v2_aligned_backtest_paper.py` for deterministic backtest/paper dataset regeneration.
- Added v2 paper parity validator `backend/paper_trading/verify_v2_parity.py`.
- Added v2 config/runtime usage guard `backend/strategy_generator/validate_v2_config_usage.py` and CI workflow `.github/workflows/validate-v2-config.yml`.
- Updated `.github/workflows/paper-trade.yml` to run aligned v2 simulation reset and v2 parity checks.
- Updated `.github/workflows/rerun-backtest-issue.yml` and `.github/workflows/rerun-paper-trade-issue.yml` for v2 rerun support.

- Added side-aware v1 long-entry evaluator in `backend/strategy_generator/apm_v1.py` and wired side dispatch in `apm_v1_latest_bar_analysis(...)` and `apm_v1_signals(...)` so runtime evaluation supports both long and short gate stacks.
- Added v1 long RSI defaults (`rsi_long_min`, `rsi_long_max`) to shared runtime params in `backend/strategy_generator/v1_params.py`.
- Updated realtime paper runner (`backend/paper_trading/realtime_alpaca_paper_trader.py`) to evaluate every symbol for both long and short opportunities each pass, with long-first selection and broker-capability enforcement at order submission.
- Updated realtime live runner (`backend/live_trading/realtime_alpaca_live_trader.py`) to evaluate both directions for every symbol, add long bracket submission support, and use side-aware risk/order parameter calculation.
- Updated paper runner exit analysis to derive side from actual broker position state for close-on-signal behavior.
- Improved dashboard log event labeling in `docs/site.js` by deriving gate/event names from detail text (for example `failed bullish_stack: ...` now surfaces `bullish_stack`).
- Added scheduler gap observability in realtime paper trading via `schedule_miss` records in `realtime_paper_log` when run cadence exceeds threshold.
- Added optional missed-window catch-up scanner in `backend/paper_trading/realtime_alpaca_paper_trader.py` (`--catchup-missed-windows`, `--catchup-max-windows`) that logs `missed_opportunity` and `missed_opportunity_blocked` entries without placing retroactive orders.

- Closed v1 backtesting guideline gap by promoting tuned ETHUSD overrides into default runtime config (backend/strategy_generator/configs/v1_runtime.json); default v1 now passes all guideline thresholds across BTC/USD, ETH/USD, CLM, and CRF.
- Added ETH profile tuning utility at backend/strategy_generator/tune_v1_profile.py with optional `--apply` to update profile overrides from reproducible search results.
- Added CI workflow .github/workflows/v1-guideline-matrix.yml with default matrix reporting plus enforced eth_focus crypto guideline gate.
- Created SQLite database (docs/data/tradingcopilot.db) with tables for backtest, paper trading, and live trading results per symbol.
- Initial changelog created.
- Added v1 parity validator at backend/paper_trading/verify_v1_parity.py to compare backtest vs paper trade rows with CI-friendly failure codes.
- Added reset_v1_aligned_backtest_paper.py to regenerate aligned v1 backtest/paper datasets from the same simulation runs.
- Updated paper/backtest rerun workflows so v1 simulation paths use aligned dataset regeneration and parity gating before DB commit.
- Completed live trading integration path: dashboard can open "Rerun Live Trading" issues and GitHub Actions now handles issue-triggered live reruns.
- Updated live trading workflow to support scheduled checks (guarded by ALLOW_ALPACA_LIVE_TRADING) and manual guarded execution.
- Added .env credential loading to the live trading runner for local execution, and fixed live fill synchronization to avoid duplicate trade inserts when fills are already recorded.
- Added repo safety gate for issue-triggered live reruns: issues now require the `approved-live-trade` label before execution.
- Added backend/live_trading/verify_live_consistency.py and wired it into live workflows to validate live fill/trade consistency after runs.
- Added shared v1 runtime parameter source at backend/strategy_generator/configs/v1_runtime.json and backend/strategy_generator/v1_params.py.
- Refactored v1 signal, backtest, paper realtime, and live realtime paths to consume shared v1 parameters to reduce strategy drift.
- Added walk-forward optimizer utility at backend/strategy_generator/walkforward_optimize_v1.py with fallback output when no folds produce valid trades.
- Added config-usage guard at backend/strategy_generator/validate_v1_config_usage.py and CI workflow .github/workflows/validate-v1-config.yml.
