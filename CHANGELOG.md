# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
- Created SQLite database (docs/data/tradingcopilot.db) with tables for backtest, paper trading, and live trading results per symbol.
- Initial changelog created.
- Added v1 parity validator at backend/paper_trading/verify_v1_parity.py to compare backtest vs paper trade rows with CI-friendly failure codes.
- Added reset_v1_aligned_backtest_paper.py to regenerate aligned v1 backtest/paper datasets from the same simulation runs.
- Updated paper/backtest rerun workflows so v1 simulation paths use aligned dataset regeneration and parity gating before DB commit.
