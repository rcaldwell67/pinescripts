# Stage 1 Instruction File for AI Coding Agents

## Purpose

This file documents the conventions, workflow, and requirements for Stage 1 parameter selection and evaluation in the strategy tuning process. It is intended to help AI coding agents and contributors maintain consistency and productivity when working with Stage 1 logic, especially for scripts like `tune_v7_btcusd.py` and related CSV outputs.

## Stage 1 Overview

- **Goal:** Identify parameter sets that achieve a minimum win rate threshold (default: 65%) in backtests.
- **Input:** Parameter grid (see `grid` in tuning scripts) and OHLCV data (cached in `data_cache/`).
- **Output:**
  - `stage1_passing_params.csv` — CSV of all parameter sets that pass the win rate guideline.
  - Each row contains parameter values and the resulting win rate.

## Workflow

1. **Parameter Grid Expansion:**
   - All combinations of grid parameters are evaluated in parallel (multiprocessing).
2. **Backtest Execution:**
   - For each parameter set, run a backtest and compute win rate:  
     $\text{Win Rate} = \frac{\text{Number of profitable trades}}{\text{Total trades}} \times 100$
3. **Filtering:**
   - Only parameter sets with win rate $\geq$ `WIN_RATE_TARGET` (default: 65%) are kept.
4. **CSV Output:**
   - Save passing parameter sets and their win rates to `stage1_passing_params.csv`.

## File Format: `stage1_passing_params.csv`

- Header: `symbol,lookback,candle-interval,win_rate,macd_fast,macd_slow,macd_signal,stoch_k_len,stoch_d_len,cci_len`
- Each row: Parameter values and win rate for a passing set.
- Example:

  ```csv
  symbol,lookback,candle-interval,win_rate,macd_fast,macd_slow,macd_signal,stoch_k_len,stoch_d_len,cci_len
  BTC/USD,YTD,15m,67.5,8,26,9,10,7,14
  ```

## Conventions & Best Practices

- Always update the CSV header if the parameter grid changes.
- Document any changes to the win rate threshold or evaluation logic.
- Use multiprocessing for efficiency.
- Cache OHLCV data to avoid redundant API calls.
- Do not edit `stage1_passing_params.csv` manually; always regenerate via script.

## Related Files

- `backend/strategy_generator/tune_v7_btcusd.py` — Main tuning script.
- `stage2_passing_params.csv`, `stage2_results.csv` — For subsequent stages.
- `README.md` — Project and dashboard documentation.

---
Last updated: 2026-04-20
