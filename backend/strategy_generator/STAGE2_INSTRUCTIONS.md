# Stage 2 Instruction File for AI Coding Agents

## Purpose
This file documents the conventions, workflow, and requirements for Stage 2 parameter evaluation in the strategy tuning process. It is intended to help AI coding agents and contributors maintain consistency and productivity when working with Stage 2 logic, especially for scripts like `tune_v7_btcusd.py` and related CSV outputs.

---

## Stage 2 Overview
- **Goal:** Evaluate all parameter sets that passed Stage 1 for their Net Return in backtests.
- **Input:** Parameter sets from `stage1_passing_params.csv` (those with win rate ≥ threshold).
- **Output:**
  - `stage2_results.csv` — CSV of all evaluated parameter sets with win rate and net return.
  - `stage2_passing_params.csv` — CSV of parameter sets that pass the Stage 2 guideline (if any, e.g., minimum net return).

## Workflow
1. **Input:**
   - Read all passing parameter sets from `stage1_passing_params.csv`.
2. **Backtest Execution:**
   - For each parameter set, run a backtest and compute:
     - Win Rate (copied from Stage 1)
     - Net Return: $\sum \text{pnl}$
3. **CSV Output:**
   - Save all results to `stage2_results.csv` (includes all evaluated sets, not just passing).
   - Optionally, filter and save passing sets to `stage2_passing_params.csv` if a net return threshold is defined.

## File Formats
- **stage2_results.csv**
  - Header: `macd_fast,macd_slow,macd_signal,stoch_k_len,stoch_d_len,cci_len,win_rate,net_return`
  - Each row: Parameter values, win rate, and net return for each evaluated set.
- **stage2_passing_params.csv**
  - Header: `symbol,lookback,candle-interval,win_rate,net_return,macd_fast,macd_slow,macd_signal,stoch_k_len,stoch_d_len,cci_len`
  - Each row: Parameter values, win rate, and net return for passing sets (if filtered).

## Conventions & Best Practices
- Always update CSV headers if the parameter grid changes.
- Document any changes to the net return threshold or evaluation logic.
- Use multiprocessing for efficiency.
- Do not edit `stage2_results.csv` or `stage2_passing_params.csv` manually; always regenerate via script.
- Document the criteria for passing Stage 2 (e.g., minimum net return) in this file and in code comments.

## Related Files
- `backend/strategy_generator/tune_v7_btcusd.py` — Main tuning script.
- `stage1_passing_params.csv` — Input for Stage 2.
- `README.md` — Project and dashboard documentation.

---

_Last updated: 2026-04-20_
