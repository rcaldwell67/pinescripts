# Backend

This folder contains all backend automation scripts for:
- Pine Script generation
- Backtesting with Backtrader
- Paper/live trading with Alpaca API

## Structure
- `generate_pinescript.py` — Generates Pine Script from CUSIP/Symbol input
- `backtest.py` — Runs backtests using Backtrader
- `trade.py` — Handles paper/live trading via Alpaca
- `utils/` — (optional) Shared utility modules

## Setup
1. Create a Python virtual environment:
   ```sh
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   ```
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

## Usage
- Scripts are designed to be run by GitHub Actions or manually for development/testing.

---

See each script for usage details and arguments.

# Development Work To Complete
- create a template for each pinescript strategy version
- ability to add symbols in the dashboard and have backtesting, paper and live trading configured automatically via Github Actions and Workflows
- ability to add values to parameters via the dashboard for items such as Win Rate, Net Return, Max Drawdown; this will allow for fine tuning Pine Script versions from the frontend

# Completed Development Work

# Strategy Guidelines
- Win Rate = 70% or greater
- Net Return = 20% or greater
- Max Drawdown = -4.50 % or less

## Guideline Matrix Report

Use the guideline report script to evaluate pass/fail by symbol and by asset class (crypto vs stocks):

```sh
python backend/strategy_generator/report_v1_guidelines.py --version v1
```

Promoted v1 closure profile:

```sh
python backend/strategy_generator/report_v1_guidelines.py --version v1 --profile guideline_closed --enforce
```

The scheduled and default manual v1 guideline workflow now uses `guideline_closed` unless you explicitly choose another profile.

Equivalent v2 run:

```sh
python backend/strategy_generator/report_v2_guidelines.py --version v2
```

Promoted v2 closure profile:

```sh
python backend/strategy_generator/report_v2_guidelines.py --version v2 --profile guideline_closed --enforce
```

The scheduled and default manual v2 guideline workflow now uses `guideline_closed` unless you explicitly choose another profile.

Useful options:

- `--asset-class crypto|stocks|all` (default `all`)
- `--symbols BTC/USD ETH/USD` (explicit symbol list)
- `--json-out docs/data/v1_guideline_report.json` (save machine-readable output)

For v2, use the same flags with `report_v2_guidelines.py` and a v2 output path like `docs/data/v2_guideline_report.json`.

## Separate Profile Backtests

You can run versioned profile overrides without editing defaults each time:

```sh
python backend/backtest_backtrader_alpaca.py --symbol ETH/USD --version v1 --profile eth_focus
```

Profile definitions live in `backend/strategy_generator/configs/v1_runtime.json` under `profiles`.

## Profile Tuning Utility

Use the profile tuner to search for per-symbol settings that maximize win rate while respecting net return and drawdown constraints:

```sh
python backend/strategy_generator/tune_v1_profile.py --symbol ETH/USD --profile eth_focus --max-evals 40 --seed 42 --out docs/data/v1_profile_tuning_result_eth.json --apply
```

One-command v1 closure loop:

```sh
python backend/strategy_generator/close_v1_guidelines.py --profile guideline_closed --skip-tune
```

Manual Actions workflow equivalent: `.github/workflows/close-v1-guidelines.yml`

Equivalent v2 run:

```sh
python backend/strategy_generator/tune_v2_profile.py --symbol ETH/USD --max-evals 120 --seed 42 --out docs/data/v2_profile_tuning_result_eth.json --apply
```

One-command v2 closure loop:

```sh
python backend/strategy_generator/close_v2_guidelines.py --profile guideline_closed
```

Manual Actions workflow equivalent: `.github/workflows/close-v2-guidelines.yml`

Notes:

- `--apply` updates the selected profile in `backend/strategy_generator/configs/v1_runtime.json`.
- The script writes the best candidate plus metrics to JSON for auditability.
- For v1, `close_v1_guidelines.py` can enforce the promoted `guideline_closed` profile directly or re-run tuning before validation.
- For v2, `close_v2_guidelines.py` re-runs tuning for the selected symbols, validates config usage, and then enforces the matrix with the chosen profile.
- The `Close V2 Guidelines` workflow runs the same closure loop in GitHub Actions and uploads the enforced report plus tuning artifacts.
