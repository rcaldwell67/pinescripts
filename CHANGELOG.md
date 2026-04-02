# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Closed v2 backtesting guideline gap by promoting validated BTCUSD and ETHUSD overrides into `backend/strategy_generator/configs/v2_runtime.json`; default v2 now passes all guideline thresholds across BTC/USD, ETH/USD, CLM, and CRF.
- Added standalone v2 guideline matrix report at `backend/strategy_generator/report_v2_guidelines.py` with JSON output and enforced failure mode.
- Expanded `backend/strategy_generator/tune_v2_profile.py` with broader search coverage, stronger win-rate-first ranking, and profile-scoped apply support.
- Added `backend/strategy_generator/close_v2_guidelines.py` to run the full v2 closure loop: retune, validate, and enforce.
- Updated `.github/workflows/v2-guideline-matrix.yml` to default scheduled and manual runs to the promoted `guideline_closed` profile.
- Added `.github/workflows/close-v2-guidelines.yml` for manual execution of the full v2 closure loop in GitHub Actions.
- Added promoted v1 `guideline_closed` profile plus `backend/strategy_generator/close_v1_guidelines.py` and `.github/workflows/close-v1-guidelines.yml` so v1 and v2 now share the same closure workflow pattern.
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
