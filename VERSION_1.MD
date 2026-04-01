# VERSION 1 (APM v1) Reference

This document describes everything that is part of version v1 across backtest, paper trading, and live trading.

## Scope

- Strategy family: Adaptive Pullback Momentum v1
- Primary timeframe: 5m
- Primary implementation language: Python (execution) plus Pine Script (strategy template)
- Current execution support in automation: v1 is the only fully wired end-to-end version for realtime paper and realtime live runners.

## Guideline Compliance Snapshot (2026-03-31)

Reference guideline targets:

- Win Rate >= 70%
- Net Return >= 20%
- Max Drawdown <= 4.50%

Latest local matrix run (`python backend/strategy_generator/report_v1_guidelines.py --version v1`):

|Symbol|Class|Trades|Win Rate|Net Return|Max Drawdown|Guideline Status|
|---|---|---:|---:|---:|---:|---|
|BTC/USD|crypto|40|70.00%|23.39%|4.38%|PASS|
|ETH/USD|crypto|101|71.29%|25.93%|1.97%|PASS|
|CLM|stocks|3|100.00%|20.75%|0.00%|PASS|
|CRF|stocks|3|100.00%|20.47%|0.00%|PASS|

Current state summary:

- 4 of 4 symbols pass all v1 guideline targets in backtesting.
- v1 backtesting guideline compliance is now closed for the default runtime profile.
- A dedicated matrix workflow exists in `.github/workflows/v1-guideline-matrix.yml`, plus an eth_focus crypto enforcement job.

ETH focused-profile progress (`eth_focus`, 2026-03-31):

- ETH/USD improved from 64.00% WR to 71.29% WR while keeping net return and drawdown within guideline limits.
- Current ETH/USD (`eth_focus`) snapshot: WR=71.29%, Net=25.93%, MaxDD=1.97%.
- These tuned ETH settings were promoted into the default ETHUSD symbol override for v1.

## v1 Architecture Diagram

```mermaid
flowchart TD
  A[APM v1 Signal Engine<br/>apm_v1.py] --> B[Backtest Engine<br/>apm_v1_backtest.py]
  A --> C[Realtime Paper Runner<br/>realtime_alpaca_paper_trader.py]
  A --> D[Realtime Live Runner<br/>realtime_alpaca_live_trader.py]

  E[OHLCV Fetch<br/>backtest_backtrader_alpaca.py] --> B
  E --> C
  E --> D

  B --> F[(trades mode=backtest)]
  C --> G[(paper_fill_events)]
  G --> H[(trades mode=paper)]
  D --> I[(live_fill_events)]
  I --> J[(trades mode=live)]

  B --> K[(backtest_results)]
  C --> L[(paper_trading_results)]
  D --> M[(live_trading_results)]

  F --> N[(tradingcopilot.db)]
  H --> N
  J --> N
  K --> N
  L --> N
  M --> N

  O[verify_v1_parity.py] --> F
  O --> H
  P[verify_live_consistency.py] --> I
  P --> J

  N --> Q[Dashboard<br/>docs/site.js + docs/index.html]

  R[GitHub Workflows<br/>backtest/paper/live + issue reruns] --> B
  R --> C
  R --> D
```

## Strategy Definition (v1)

### Pine strategy source

- File: `backend/pine_templates/APM v1.0-5m.pine`
- Purpose:
  - Canonical Pine strategy template for v1.
  - Contains entry/exit logic, risk controls, plotting, and dashboard overlays in TradingView.

### Python signal engine

- File: `backend/strategy_generator/apm_v1.py`
- Function: `apm_v1_signals(df)`
- Purpose:
  - Generates v1 entry indices from OHLCV and indicators.
  - Used by backtest, paper, and live runners.

### Python backtest engine

- File: `backend/strategy_generator/apm_v1_backtest.py`
- Function: `backtest_apm_v1(df)`
- Purpose:
  - Simulates v1 trades and equity curve from signal indices.
  - Uses ATR-based SL/TP/trailing logic and risk sizing.

### Local standalone backtest runner

- File: `backend/strategy_generator/run_apm_v1_backtest.py`
- Purpose:
  - Convenience script that loads local CSV and writes v1 trades CSV.

## Shared Data + DB Infrastructure

### Main database

- File: `docs/data/tradingcopilot.db`
- Purpose:
  - Single source for dashboard-backed trading data.
  - Stores symbols, trade rows, and summary rows for backtest/paper/live modes.
  - Now also stores account metadata and balances in `Account_Info` for Alpaca paper account display/update flows.

### Account info tracking

- Table: `Account_Info`
- Purpose:
  - Stores Alpaca account id, account number, status, beginning balance, current balance, buying power, cash, last event, and update timestamp.
  - Used by realtime paper trading to keep dashboard-visible account balance state in sync with Alpaca account activity.

### Shared fetch/backtest utilities

- File: `backend/backtest_backtrader_alpaca.py`
- Key elements used by v1 components:
  - `DB_PATH`
  - `VERSION_MAP`
  - `fetch_ohlcv(...)`
  - `run_backtest(...)` for v1 path

## v1 Backtest Components

### Backtest runner (symbol + version)

- File: `backend/backtest_backtrader_alpaca.py`
- CLI usage:
  - `python backend/backtest_backtrader_alpaca.py --symbol "BTC/USD" --version v1`
- Behavior:
  - Fetches OHLCV.
  - Runs v1 backtest.
  - Persists summary to DB (`backtest_results`).

### v1 aligned backtest/paper reset

- File: `reset_v1_aligned_backtest_paper.py`
- CLI usage:
  - `python reset_v1_aligned_backtest_paper.py --symbol "BTC/USD"`
  - `python reset_v1_aligned_backtest_paper.py`
- Behavior:
  - Regenerates v1 rows for both `mode='backtest'` and `mode='paper'` from a single simulation output.
  - Rewrites v1 summary rows in `backtest_results` and `paper_trading_results`.
  - Creates DB backup before rewrite.

### Backtest rerun workflow trigger

- File: `.github/workflows/rerun-backtest-issue.yml`
- Trigger format:
  - GitHub issue title starts with `Rerun Backtest:`
- v1 behavior:
  - Uses `reset_v1_aligned_backtest_paper.py` when version is v1.

## v1 Paper Trading Components

### Realtime paper runner

- File: `backend/paper_trading/realtime_alpaca_paper_trader.py`
- CLI usage:
  - `python backend/paper_trading/realtime_alpaca_paper_trader.py --symbol CLM --version v1`
  - `python backend/paper_trading/realtime_alpaca_paper_trader.py --all-symbols --version v1`
- Behavior:
  - Reads v1 signal from latest bars.
  - Submits Alpaca paper bracket orders.
  - Uses long-side paper execution for crypto symbols and short-side execution for supported non-crypto symbols.
  - Syncs fill activities into `paper_fill_events`.
  - Syncs canceled/rejected/expired order events into `paper_order_events`.
  - Tracks order-to-trade links in `paper_order_trade_links`.
  - Mirrors fills into `trades` rows with `mode='paper'`.
  - Updates `Account_Info` on heartbeat, fill, and cancel events.
  - Writes status summaries to `paper_trading_results`.
  - Supports optional loop monitoring, websocket bar triggers, open-position caps, and signal-driven close behavior.

### Simulation paper runner (non-realtime)

- File: `backend/paper_trading/paper_trade_backtrader_alpaca.py`
- Purpose:
  - Simulation-based paper mode path used in some workflows for non-v1 or explicit simulation runs.

### Parity validator (v1)

- File: `backend/paper_trading/verify_v1_parity.py`
- CLI usage:
  - `python backend/paper_trading/verify_v1_parity.py --version v1`
  - `python backend/paper_trading/verify_v1_parity.py --version v1 --symbol BTC/USD`
- Behavior:
  - Compares `mode='backtest'` vs `mode='paper'` v1 trade rows.
  - CI-friendly non-zero exit code on mismatch.

### Paper trading workflows

- File: `.github/workflows/paper-trade.yml`
- Triggers:
  - Scheduled and manual
- v1 behavior:
  - Defaults to version v1.
  - Supports `execution_mode` realtime or simulation.
  - Realtime path now supports `max_open_positions`, `close_on_signal`, and manual-only `stream_bars` options.
  - Includes optional v1 parity check in simulation flow.

### Paper rerun workflow trigger

- File: `.github/workflows/rerun-paper-trade-issue.yml`
- Trigger format:
  - GitHub issue title starts with `Rerun Paper Trading:`
- v1 behavior:
  - Runs realtime Alpaca paper trading for v1.
  - Uses a dedicated concurrency lane so dashboard-triggered paper reruns are not blocked behind unrelated DB-writer jobs.

## v1 Live Trading Components

### Realtime live runner

- File: `backend/live_trading/realtime_alpaca_live_trader.py`
- CLI usage:
  - `python backend/live_trading/realtime_alpaca_live_trader.py --symbol CLM --version v1`
  - `python backend/live_trading/realtime_alpaca_live_trader.py --all-symbols --version v1`
- Behavior:
  - Loads `.env` if available.
  - Enforces safety lock: requires `ALLOW_ALPACA_LIVE_TRADING=true|1|yes`.
  - Uses v1 signal engine, computes order params, submits short bracket orders.
  - Syncs live fills into `live_fill_events`.
  - Mirrors live fills into `trades` rows with `mode='live'`.
  - Writes status summaries to `live_trading_results`.

### Live consistency validator

- File: `backend/live_trading/verify_live_consistency.py`
- CLI usage:
  - `python backend/live_trading/verify_live_consistency.py --version v1`
  - `python backend/live_trading/verify_live_consistency.py --symbol CLM --version v1`
- Behavior:
  - Reconciles `live_fill_events` with `trades(mode='live')` counts.
  - Fails on mismatched open/closed counts or invalid fill-side relationships.

### Live trading workflow (scheduled/manual)

- File: `.github/workflows/live-trade.yml`
- Triggers:
  - `schedule` (every 5 minutes)
  - `workflow_dispatch`
- Behavior:
  - Guarded execution based on `ALLOW_ALPACA_LIVE_TRADING`.
  - Runs live trader and then live consistency validator.

### Live rerun via issue (approval-gated)

- File: `.github/workflows/rerun-live-trade-issue.yml`
- Trigger format:
  - GitHub issue title starts with `Rerun Live Trading:`
- Safety gate:
  - Requires issue label `approved-live-trade`.
  - Unapproved issue requests are commented and closed.
- Behavior:
  - Runs live trader for requested symbol/version.
  - Runs live consistency validator.
  - Commits DB changes, comments result, closes issue.

## Dashboard Integration for v1

### Frontend behavior

- File: `docs/site.js`
- v1-specific integration:
  - `PAPER_TRADING_SUPPORTED_VERSIONS` includes `v1`.
  - `LIVE_TRADING_SUPPORTED_VERSIONS` includes `v1`.
  - Shows rerun buttons by dataset mode for selected version.
  - Opens issue-based rerun requests for backtest, paper, and live.
  - Supports dynamic account display via `Account_Info`.
  - Includes paper/live/backtest mode-aware balance handling.
- Ticker enhancements (2026-03-31):
  - Result Badge component displays risk management type indicators (Take Profit, Stop Loss, Trailing Stop).
  - Color-coded badges: green for TP, red for SL, orange for Trail.
  - Badges render inline below ticker symbol for compact at-a-glance risk visibility.

### Frontend shell

- File: `docs/index.html`
- Contains dataset mode selector for:
  - Backtest
  - Paper Trading
  - Live Trading
  - Includes an `Account Info` modal to display Alpaca account balances and metadata from the database.
- Stylesheet: `docs/site.css`
  - Ticker badge styling added (2026-03-31):
    - `.ticker-badge-tp`: Green badge for Take Profit targets
    - `.ticker-badge-sl`: Red badge for Stop Loss levels
    - `.ticker-badge-trail`: Orange badge for Trailing Stop indicators

### Chart data refresh path

- File: `docs/fetch_chart_data.py`
- Current behavior:
  - Uses Alpaca crypto bars for BTC/USD and ETH/USD.
  - Uses Alpaca stock bars via IEX feed for stocks where available.
  - Falls back to Yahoo Finance hourly bars for stock symbols when Alpaca subscription/feed access is unavailable.

## Environment Variables Used by v1

### Core Alpaca credentials

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`

### Paper-specific (preferred by paper runner)

- `ALPACA_PAPER_API_KEY`
- `ALPACA_PAPER_API_SECRET`

### Live-specific (preferred by live runner)

- `ALPACA_LIVE_API_KEY`
- `ALPACA_LIVE_API_SECRET`
- Optional: `ALPACA_LIVE_BASE_URL`

### Live safety lock

- `ALLOW_ALPACA_LIVE_TRADING`
  - Required true/1/yes for live order placement.

## Known v1 Constraints

- Realtime paper/live scripts currently allow only `--version v1`.
- Realtime paper/live wiring is still version-gated to v1 even though template/config scaffolding exists for later versions.
- Paper execution uses symbol-aware side targeting rather than a uniform long/short implementation across all asset classes.
- Stock chart refresh quality can vary by available feed; unsupported recent Alpaca stock requests fall back to Yahoo Finance hourly data.

## Paper Trading Reset State (2026-03-31)

- Historical paper-trading rows were archived and active paper rows were reset to start realtime paper from a clean slate.
- Archive tables now hold prior paper history:
  - `paper_trades_archive`
  - `paper_trading_results_archive`
  - `paper_fill_events_archive`
  - `paper_order_trade_links_archive`
  - `paper_order_events_archive`
- `Account_Info.last_event` was updated to `paper_reset` during reset.
- Non-v1 versions may exist as templates/configs, but v1 has the most complete operational wiring across backtest/paper/live.

## Operational Runbook (v1)

### Backtest-only rerun (single symbol)

1. Run:
   - `python reset_v1_aligned_backtest_paper.py --symbol "BTC/USD"`
2. Optional validation:
   - `python backend/paper_trading/verify_v1_parity.py --version v1 --symbol "BTC/USD"`

### Paper realtime cycle (single symbol)

1. Run:

   - `python backend/paper_trading/realtime_alpaca_paper_trader.py --symbol CLM --version v1`

   - Optional monitored loop:

     - `python backend/paper_trading/realtime_alpaca_paper_trader.py --symbol CLM --version v1 --loop-seconds 60 --max-open-positions 8`

   - Optional event-driven manual mode:

     - `python backend/paper_trading/realtime_alpaca_paper_trader.py --symbol BTC/USD --version v1 --stream-bars`

1. Validate parity if using simulation reset path:

   - `python backend/paper_trading/verify_v1_parity.py --version v1 --symbol CLM`

### Live realtime cycle (single symbol, guarded)

1. Set safety lock:
   - `ALLOW_ALPACA_LIVE_TRADING=true`
2. Run:
   - `python backend/live_trading/realtime_alpaca_live_trader.py --symbol CLM --version v1`
3. Validate consistency:
   - `python backend/live_trading/verify_live_consistency.py --symbol CLM --version v1`

## Quick File Index (v1)

- `backend/pine_templates/APM v1.0-5m.pine`
- `backend/strategy_generator/apm_v1.py`
- `backend/strategy_generator/apm_v1_backtest.py`
- `backend/strategy_generator/run_apm_v1_backtest.py`
- `backend/backtest_backtrader_alpaca.py`
- `reset_v1_aligned_backtest_paper.py`
- `backend/paper_trading/realtime_alpaca_paper_trader.py`
- `backend/paper_trading/paper_trade_backtrader_alpaca.py`
- `backend/paper_trading/verify_v1_parity.py`
- `backend/data/create_tradingcopilot_db.py`
- `backend/live_trading/realtime_alpaca_live_trader.py`
- `backend/live_trading/verify_live_consistency.py`
- `.github/workflows/rerun-backtest-issue.yml`
- `.github/workflows/rerun-paper-trade-issue.yml`
- `.github/workflows/paper-trade.yml`
- `.github/workflows/alpaca-paper-sync.yml`
- `.github/workflows/live-trade.yml`
- `.github/workflows/rerun-live-trade-issue.yml`
- `docs/index.html`
- `docs/site.js`
- `docs/site.css`
- `docs/fetch_chart_data.py`
- `docs/data/tradingcopilot.db`
