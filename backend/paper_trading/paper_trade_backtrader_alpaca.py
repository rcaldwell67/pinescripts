"""
Generic paper-trading runner for any symbol in tradingcopilot.db.

This reuses the implemented strategy engine(s) from the backtest runner,
simulates paper trades from the latest fetched market data, and stores both
trade rows and summary metrics in tradingcopilot.db.

Usage:
    python backend/paper_trading/paper_trade_backtrader_alpaca.py --symbol "BTC/USD" --version v1
    python backend/paper_trading/paper_trade_backtrader_alpaca.py --all-symbols --version v1
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from backtest_backtrader_alpaca import DB_PATH, VERSION_MAP, _to_native, fetch_ohlcv, run_backtest


def _result_label(exit_type: object) -> str:
    value = str(exit_type or "").strip().lower()
    if value == "take_profit":
        return "TP"
    if value == "stop_loss":
        return "SL"
    if value == "max_bars_exit":
        return "MB"
    if "trail" in value:
        return "TRAIL"
    return str(exit_type or "OTHER").upper()


def _timestamp_at(df, idx: object) -> str | None:
    try:
        pos = int(idx)
        if pos < 0 or pos >= len(df):
            return None
        return str(df["timestamp"].iloc[pos])
    except Exception:
        return None


def _metrics_for_trades(symbol: str, version: str, trades, df) -> dict[str, object]:
    pnl_col = "pnl" if "pnl" in trades.columns else "dollar_pnl"
    equity_col = "equity"

    total_trades = len(trades)
    initial_equity = float(trades[equity_col].iloc[0] - trades[pnl_col].iloc[0]) if total_trades else 10000.0
    final_equity = float(trades[equity_col].iloc[-1]) if total_trades else initial_equity
    win_trades = int((trades[pnl_col] > 0).sum()) if total_trades else 0
    loss_trades = int((trades[pnl_col] <= 0).sum()) if total_trades else 0
    win_rate = win_trades / total_trades * 100 if total_trades else 0.0
    avg_pnl = float(trades[pnl_col].mean()) if total_trades else 0.0
    total_pnl = float(trades[pnl_col].sum()) if total_trades else 0.0
    max_drawdown = float((trades[equity_col].cummax() - trades[equity_col]).max()) if total_trades else 0.0
    net_return_pct = ((final_equity - initial_equity) / initial_equity * 100) if initial_equity else 0.0

    first_trade_date = _timestamp_at(df, trades["entry_idx"].iloc[0]) if total_trades and "entry_idx" in trades.columns else None
    last_trade_date = _timestamp_at(df, trades["entry_idx"].iloc[-1]) if total_trades and "entry_idx" in trades.columns else None

    return {
        "symbol": symbol,
        "version": version,
        "beginning_equity": _to_native(initial_equity),
        "final_equity": _to_native(final_equity),
        "total_trades": _to_native(total_trades),
        "winning_trades": _to_native(win_trades),
        "losing_trades": _to_native(loss_trades),
        "win_rate": _to_native(win_rate),
        "average_pnl": _to_native(avg_pnl),
        "total_pnl": _to_native(total_pnl),
        "max_drawdown": _to_native(max_drawdown),
        "net_return_pct": _to_native(net_return_pct),
        "first_trade_date": first_trade_date,
        "last_trade_date": last_trade_date,
    }


def save_paper_to_db(symbol: str, version: str, trades, df) -> None:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    notes = f"{VERSION_MAP.get(version, version)} paper trading summary"
    conn.execute(
        "DELETE FROM trades WHERE symbol = ? AND version = ? AND mode = 'paper'",
        (symbol, version),
    )
    conn.execute(
        "DELETE FROM paper_trading_results WHERE symbol = ? AND notes LIKE ?",
        (symbol, f"%{VERSION_MAP.get(version, version)}%"),
    )

    metrics = _metrics_for_trades(symbol, version, trades, df)
    conn.execute(
        "INSERT INTO paper_trading_results (symbol, metrics, notes) VALUES (?, ?, ?)",
        (symbol, json.dumps(metrics), notes),
    )

    if not trades.empty:
        for _, row in trades.iterrows():
            entry_time = _timestamp_at(df, row.get("entry_idx"))
            exit_time = _timestamp_at(df, row.get("exit_idx"))
            dollar_pnl = float(row.get("pnl", row.get("dollar_pnl", 0.0)) or 0.0)
            equity = float(row.get("equity", 0.0) or 0.0)
            beginning_equity = equity - dollar_pnl
            pnl_pct = (dollar_pnl / beginning_equity * 100.0) if beginning_equity else None
            conn.execute(
                """
                INSERT INTO trades (
                    symbol, version, mode, entry_time, exit_time, direction,
                    entry_price, exit_price, result, pnl_pct, dollar_pnl, equity
                ) VALUES (?, ?, 'paper', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    version,
                    entry_time,
                    exit_time,
                    "short",
                    float(row.get("entry", 0.0) or 0.0),
                    float(row.get("exit", 0.0) or 0.0),
                    _result_label(row.get("exit_type")),
                    pnl_pct,
                    dollar_pnl,
                    equity,
                ),
            )

    conn.commit()
    conn.close()
    print(
        f"Paper results saved to DB: {symbol} {version} "
        f"trades={metrics['total_trades']} net={metrics['net_return_pct']:.1f}%"
    )


def load_symbols_from_db() -> list[str]:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    rows = conn.execute("SELECT symbol FROM symbols ORDER BY symbol").fetchall()
    conn.close()
    return [row[0] for row in rows]


def run_one(symbol: str, version: str) -> None:
    print(f"Fetching YTD OHLCV for {symbol}...")
    df = fetch_ohlcv(symbol)
    print(f"  {len(df):,} bars fetched ({df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]})")

    print(f"Running paper-trading simulation {version} for {symbol}...")
    trades = run_backtest(df, version)
    print(f"  {len(trades)} trades generated")
    save_paper_to_db(symbol, version, trades, df)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paper-trading simulation(s) and save them to the DB.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--symbol", help="Trading symbol, e.g. BTC/USD")
    scope.add_argument("--all-symbols", action="store_true", help="Run for every symbol in the DB")
    parser.add_argument("--version", required=True, help="Strategy version, e.g. v1")
    args = parser.parse_args()

    version = args.version.strip().lower()
    if version not in VERSION_MAP:
        print(f"ERROR: version {version!r} is not implemented. Valid: {list(VERSION_MAP)}", file=sys.stderr)
        return 1

    symbols = [args.symbol.strip()] if args.symbol else load_symbols_from_db()
    if not symbols:
        print("No symbols found in tradingcopilot.db; nothing to run.")
        return 0

    failures: list[str] = []
    for symbol in symbols:
        try:
            run_one(symbol, version)
        except Exception as exc:
            print(f"ERROR: Paper trading failed for {symbol} {version}: {exc}", file=sys.stderr)
            failures.append(symbol)

    if failures:
        print(f"Paper trading failures: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())