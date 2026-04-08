"""
Generic paper-trading runner for any symbol in tradingcopilot.db.

This reuses the implemented strategy engine(s) from the backtest runner,
simulates paper trades from the latest fetched market data, and stores both
trade rows and summary metrics in tradingcopilot.db.

Usage:
    python backend/paper_trading/paper_trade_backtrader_alpaca.py --symbol "BTC/USD" --version v1
    python backend/paper_trading/paper_trade_backtrader_alpaca.py --all-symbols --version v6
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

from backtest_backtrader_alpaca import (
    DB_PATH,
    VERSION_MAP,
    _to_native,
    ensure_result_tables_have_current_equity,
    fetch_ohlcv,
    run_backtest,
)


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
    initial_equity = float(trades[equity_col].iloc[0] - trades[pnl_col].iloc[0]) if total_trades else 100000.0
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
        "current_equity": _to_native(final_equity),
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


def save_paper_to_db(symbol: str, version: str, trades, df, *, force_reset: bool = False) -> None:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=DELETE")
    ensure_result_tables_have_current_equity(conn)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass

    notes = f"{VERSION_MAP.get(version, version)} paper trading summary"

    if force_reset:
        conn.execute(
            "DELETE FROM trades WHERE symbol = ? AND version = ? AND mode = 'paper'",
            (symbol, version),
        )
        last_exit_time = None
    else:
        row = conn.execute(
            "SELECT MAX(exit_time) FROM trades WHERE symbol = ? AND version = ? AND mode = 'paper'",
            (symbol, version),
        ).fetchone()
        last_exit_time = row[0] if row else None

    # Build new trade rows, skipping any already stored
    new_rows: list[tuple] = []
    skipped = 0

    if not trades.empty:
        for _, trade in trades.iterrows():
            entry_time = _timestamp_at(df, trade.get("entry_idx"))
            exit_time = _timestamp_at(df, trade.get("exit_idx"))

            if last_exit_time and entry_time and entry_time <= last_exit_time:
                skipped += 1
                continue

            dollar_pnl = float(trade.get("pnl", trade.get("dollar_pnl", 0.0)) or 0.0)
            equity = float(trade.get("equity", 0.0) or 0.0)
            beginning_equity = equity - dollar_pnl
            pnl_pct = (dollar_pnl / beginning_equity * 100.0) if beginning_equity else None
            direction = str(trade.get("side", "short") or "short").strip().lower()
            if direction not in {"long", "short"}:
                direction = "short"

            new_rows.append((
                symbol,
                version,
                entry_time,
                exit_time,
                direction,
                float(trade.get("entry", 0.0) or 0.0),
                float(trade.get("exit", 0.0) or 0.0),
                _result_label(trade.get("exit_type")),
                pnl_pct,
                dollar_pnl,
                equity,
            ))

    if new_rows:
        conn.executemany(
            """
            INSERT INTO trades (
                symbol, version, mode, entry_time, exit_time, direction,
                entry_price, exit_price, result, pnl_pct, dollar_pnl, equity
            ) VALUES (?, ?, 'paper', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            new_rows,
        )

    # Always refresh the summary metrics from the full simulation run
    metrics = _metrics_for_trades(symbol, version, trades, df)
    conn.execute(
        "DELETE FROM paper_trading_results WHERE symbol = ? AND notes LIKE ?",
        (symbol, f"%{VERSION_MAP.get(version, version)}%"),
    )
    conn.execute(
        "INSERT INTO paper_trading_results (symbol, metrics, notes, current_equity) VALUES (?, ?, ?, ?)",
        (symbol, json.dumps(metrics), notes, float(metrics.get("current_equity") or metrics.get("final_equity") or 0.0)),
    )

    conn.commit()
    conn.close()
    print(
        f"Paper results saved: {symbol} {version} "
        f"new={len(new_rows)} skipped={skipped} net={metrics['net_return_pct']:.1f}%"
    )


def load_symbols_from_db() -> list[str]:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    rows = conn.execute("SELECT symbol FROM symbols ORDER BY symbol").fetchall()
    conn.close()
    return [row[0] for row in rows]


def run_one(
    symbol: str,
    version: str,
    *,
    force_reset: bool = False,
    prefer_realtime_data: bool = False,
    realtime_only_data: bool = False,
    data_scope: str = "historical",
) -> None:
    print(f"Fetching YTD OHLCV for {symbol}...")
    df = fetch_ohlcv(
        symbol,
        prefer_realtime_bar=prefer_realtime_data,
        alpaca_only=realtime_only_data,
        data_scope=data_scope,
    )
    print(f"  {len(df):,} bars fetched ({df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]})")

    print(f"Running paper-trading simulation {version} for {symbol}...")
    trades = run_backtest(df, version, symbol=symbol)
    print(f"  {len(trades)} trades generated")
    save_paper_to_db(symbol, version, trades, df, force_reset=force_reset)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paper-trading simulation(s) and save them to the DB.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--symbol", help="Trading symbol, e.g. BTC/USD")
    scope.add_argument("--all-symbols", action="store_true", help="Run for every symbol in the DB")
    parser.add_argument("--version", required=True, help="Strategy version (v1-v6)")
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="Delete and regenerate all paper trades instead of appending new ones",
    )
    parser.add_argument(
        "--prefer-realtime-data",
        action="store_true",
        help="Attempt to append the latest Alpaca realtime bar when building simulation OHLCV",
    )
    parser.add_argument(
        "--realtime-only-data",
        action="store_true",
        help="Require Alpaca data source only (disable Yahoo fallback)",
    )
    parser.add_argument(
        "--data-scope",
        choices=["historical", "same_day"],
        default="historical",
        help="Simulation data scope: full historical window or same UTC day only",
    )
    args = parser.parse_args()


    # Force v6 for all paper trading
    version = "v6"

    symbols = [args.symbol.strip()] if args.symbol else load_symbols_from_db()
    if not symbols:
        print("No symbols found in tradingcopilot.db; nothing to run.")
        return 0

    failures: list[str] = []
    for symbol in symbols:
        try:
            run_one(
                symbol,
                version,
                force_reset=args.force_reset,
                prefer_realtime_data=args.prefer_realtime_data,
                realtime_only_data=args.realtime_only_data,
                data_scope=args.data_scope,
            )
        except Exception as exc:
            print(f"ERROR: Paper trading failed for {symbol} {version}: {exc}", file=sys.stderr)
            failures.append(symbol)

    if failures:
        print(f"Paper trading failures: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())