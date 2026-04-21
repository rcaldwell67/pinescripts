# Stage 3 Instruction File for AI Coding Agents

## Purpose
This file documents the conventions, workflow, and requirements for Stage 3 parameter evaluation in the strategy tuning process. It is intended to help AI coding agents and contributors maintain consistency and productivity when working with Stage 3 logic, especially for scripts like `tune_v7_btcusd.py` and related CSV outputs.

---

## Stage 3 Overview
- **Goal:** Evaluate all parameter sets that passed Stage 2 for additional criteria, typically maximum drawdown (MaxDD), risk-adjusted return (e.g., Calmar ratio), or other advanced metrics.
- **Input:** Parameter sets from `stage2_passing_params.csv` (those with win rate and net return ≥ thresholds).
- **Output:**
  - `stage3_results.csv` — CSV of all evaluated parameter sets with win rate, net return, and Stage 3 metrics (e.g., max drawdown, Calmar ratio).
  - `stage3_passing_params.csv` — CSV of parameter sets that pass the Stage 3 guideline (if any, e.g., max drawdown ≤ threshold, Calmar ≥ threshold).

## Workflow
1. **Input:**
   - Read all passing parameter sets from `stage2_passing_params.csv`.
2. **Backtest Execution:**
   - For each parameter set, run a backtest and compute:
     - Win Rate (from Stage 1)
     - Net Return (from Stage 2)
     - Max Drawdown, Calmar ratio, or other advanced metrics
3. **CSV Output:**
   - Save all results to `stage3_results.csv` (includes all evaluated sets, not just passing).
   - Optionally, filter and save passing sets to `stage3_passing_params.csv` if thresholds are defined.

## File Formats
- **stage3_results.csv**
  - Header: `macd_fast,macd_slow,macd_signal,stoch_k_len,stoch_d_len,cci_len,win_rate,net_return,max_drawdown,calmar_ratio,...`
  - Each row: Parameter values, win rate, net return, and Stage 3 metrics for each evaluated set.
- **stage3_passing_params.csv**
  - Header: `symbol,lookback,candle-interval,win_rate,net_return,max_drawdown,calmar_ratio,macd_fast,macd_slow,macd_signal,stoch_k_len,stoch_d_len,cci_len`
  - Each row: Parameter values and metrics for passing sets (if filtered).

## Conventions & Best Practices
- Always update CSV headers if the parameter grid or metrics change.
- Document any changes to the Stage 3 thresholds or evaluation logic.
- Use multiprocessing for efficiency.
- Do not edit `stage3_results.csv` or `stage3_passing_params.csv` manually; always regenerate via script.
- Document the criteria for passing Stage 3 (e.g., max drawdown ≤ threshold, Calmar ≥ threshold) in this file and in code comments.

## Related Files
- `backend/strategy_generator/tune_v7_btcusd.py` — Main tuning script.
- `stage2_passing_params.csv` — Input for Stage 3.
- `README.md` — Project and dashboard documentation.

---

_Last updated: 2026-04-20_
