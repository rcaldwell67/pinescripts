"""
CLI entry point for running a backtest on a symbol+version pair.
Fetches YTD 5-minute OHLCV data from Alpaca, runs the strategy,
and writes a summary row to docs/data/tradingcopilot.db.

Usage:
    python backend/backtest_backtrader_alpaca.py --symbol "BTC/USD" --version v1

Requires env vars (or a .env file):
    ALPACA_API_KEY / ALPACA_PAPER_API_KEY
    ALPACA_API_SECRET / ALPACA_PAPER_API_SECRET
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Bootstrap path so strategy_generator imports work ─────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
SG_DIR    = REPO_ROOT / "backend" / "strategy_generator"
sys.path.insert(0, str(SG_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY")    or os.getenv("ALPACA_PAPER_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_PAPER_API_SECRET")

DB_PATH = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"

VERSION_MAP: dict[str, str] = {
    "v1": "APM v1.0-5m",
    # extend here as new versions are added
}


# ── Data fetch ─────────────────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str) -> "pd.DataFrame":
    import pandas as pd
    from datetime import timedelta
    from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit  # type: ignore[attr-defined]

    now   = datetime.now(tz=timezone.utc)
    start = datetime(now.year, 1, 1, tzinfo=timezone.utc)   # YTD

    tf = TimeFrame(5, TimeFrameUnit.Minute)

    is_crypto = "/" in symbol
    if is_crypto:
        client = CryptoHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
        req    = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start, end=now)
        df     = client.get_crypto_bars(req).df
    else:
        client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
        req    = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start, end=now)
        df     = client.get_stock_bars(req).df

    if df.empty:
        raise RuntimeError(f"No data returned from Alpaca for {symbol}")

    df = df.reset_index()
    # Multi-symbol DataFrames have a 'symbol' column; keep our symbol only
    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol]

    # Normalise timestamp column
    ts_col = next((c for c in ("timestamp", "time") if c in df.columns), df.columns[0])
    df = df.rename(columns={ts_col: "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Rename to Title-case for strategy modules that expect Close/High/Low/Open/Volume
    col_map = {c: c.capitalize() for c in ("open", "high", "low", "close", "volume")}
    df = df.rename(columns=col_map)
    return df


# ── Run strategy ───────────────────────────────────────────────────────────────

def run_backtest(df: "pd.DataFrame", version: str) -> "pd.DataFrame":
    if version == "v1":
        from apm_v1_backtest import backtest_apm_v1
        return backtest_apm_v1(df)
    raise ValueError(f"Unknown version: {version!r}. Valid values: {list(VERSION_MAP)}")


# ── Persist results ────────────────────────────────────────────────────────────

def _to_native(val):
    if hasattr(val, "item"):
        return val.item()
    if hasattr(val, "to_pydatetime"):
        return str(val)
    return val


def save_to_db(symbol: str, version: str,
               trades: "pd.DataFrame", df: "pd.DataFrame") -> None:
    if trades.empty:
        print("No trades generated — skipping DB write.")
        return

    pnl_col    = "pnl"       if "pnl"       in trades.columns else "dollar_pnl"
    equity_col = "equity"    if "equity"     in trades.columns else "equity"

    initial_equity = trades[equity_col].iloc[0] - trades[pnl_col].iloc[0]
    final_equity   = trades[equity_col].iloc[-1]
    total_trades   = len(trades)
    win_trades     = int((trades[pnl_col] > 0).sum())
    loss_trades    = int((trades[pnl_col] <= 0).sum())
    win_rate       = win_trades / total_trades * 100 if total_trades else 0
    avg_pnl        = float(trades[pnl_col].mean())
    total_pnl      = float(trades[pnl_col].sum())
    max_drawdown   = float((trades[equity_col].cummax() - trades[equity_col]).max())
    net_return_pct = (final_equity - initial_equity) / initial_equity * 100 if initial_equity else 0

    # Map entry_idx → timestamp if available
    first_trade_date = last_trade_date = None
    if "entry_idx" in trades.columns and "timestamp" in df.columns:
        try:
            first_trade_date = str(df["timestamp"].iloc[int(trades["entry_idx"].iloc[0])])
            last_trade_date  = str(df["timestamp"].iloc[int(trades["entry_idx"].iloc[-1])])
        except Exception:
            pass

    metrics = {
        "version":          version,
        "beginning_equity": _to_native(initial_equity),
        "final_equity":     _to_native(final_equity),
        "total_trades":     _to_native(total_trades),
        "winning_trades":   _to_native(win_trades),
        "losing_trades":    _to_native(loss_trades),
        "win_rate":         _to_native(win_rate),
        "average_pnl":      _to_native(avg_pnl),
        "total_pnl":        _to_native(total_pnl),
        "max_drawdown":     _to_native(max_drawdown),
        "net_return_pct":   _to_native(net_return_pct),
        "first_trade_date": first_trade_date,
        "last_trade_date":  last_trade_date,
    }

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # Replace the existing summary row for this symbol+version (if any)
    notes = f"{VERSION_MAP.get(version, version)} backtest summary"
    conn.execute(
        "DELETE FROM backtest_results WHERE symbol = ? AND notes LIKE ?",
        (symbol, f"%{VERSION_MAP.get(version, version)}%"),
    )
    conn.execute(
        "INSERT INTO backtest_results (symbol, metrics, notes) VALUES (?, ?, ?)",
        (symbol, json.dumps(metrics), notes),
    )
    conn.commit()
    conn.close()
    print(f"Results saved to DB: {symbol} {version}  "
          f"trades={total_trades}  net={net_return_pct:.1f}%")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Run an APM backtest and save results to the DB.")
    parser.add_argument("--symbol",  required=True, help="Trading symbol, e.g. BTC/USD")
    parser.add_argument("--version", required=True, help="Strategy version, e.g. v1")
    args = parser.parse_args()

    symbol  = args.symbol.strip()
    version = args.version.strip().lower()

    if version not in VERSION_MAP:
        print(f"ERROR: version {version!r} is not implemented. Valid: {list(VERSION_MAP)}",
              file=sys.stderr)
        return 1

    print(f"Fetching YTD 5m OHLCV for {symbol}...")
    df = fetch_ohlcv(symbol)
    print(f"  {len(df):,} bars fetched ({df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]})")

    print(f"Running backtest {version}...")
    trades = run_backtest(df, version)
    print(f"  {len(trades)} trades generated")

    save_to_db(symbol, version, trades, df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
