# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
