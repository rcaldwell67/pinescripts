# VERSION 2 (APM v2) Reference

This document describes what is currently implemented for APM v2 in this repository.

## Scope

- Strategy family: Adaptive Pullback Momentum v2
- Primary timeframe: 10m
- Primary implementation language: Pine Script
- Current support state:
  - Pine/template and dashboard dataset support: available
  - Python backtest/paper/live execution support under `--version v2`: not currently wired

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

## Execution Support Status (Important)

Current Python automation is v1-centric.

- There is no active backend execution path in this repo that dispatches strategy logic for `version == "v2"` in the current Python trading/backtest runners.
- Realtime paper and live runners currently operate on v1 signal-engine wiring.
- v2 is therefore documented and represented primarily through Pine/template + dashboard dataset flows at this time.

## Recommended Next Steps To Fully Wire v2

1. Add a Python v2 signal/backtest engine module and parameter source (mirroring v1 architecture).
2. Extend runtime dispatch in shared backtest/paper/live runners to accept `--version v2`.
3. Add parity validation for v2 (backtest vs paper dataset consistency checks).
4. Add workflow support for v2 reruns and CI checks similar to v1.
5. Update changelog/release notes when v2 execution support becomes end-to-end.
