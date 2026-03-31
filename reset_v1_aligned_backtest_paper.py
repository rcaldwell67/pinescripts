"""Regenerate aligned v1 backtest/paper datasets in tradingcopilot.db.

This script runs the same v1 backtest simulation once per symbol and writes
identical trade rows into both mode='backtest' and mode='paper' so parity
validation can operate on aligned inputs.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "strategy_generator"))

from backtest_backtrader_alpaca import DB_PATH, VERSION_MAP, fetch_ohlcv, run_backtest  # noqa: E402
from paper_trading.paper_trade_backtrader_alpaca import _metrics_for_trades, _result_label, _timestamp_at  # noqa: E402

VERSION = "v1"
VERSION_NOTE = VERSION_MAP[VERSION]


def _backup_db(db_path: Path) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup = db_path.with_name(f"{db_path.stem}.pre_align_v1_{stamp}{db_path.suffix}")
    backup.write_bytes(db_path.read_bytes())
    return backup


def _load_symbols(conn: sqlite3.Connection, symbol: str | None) -> list[str]:
    if symbol:
        return [symbol.strip()]
    rows = conn.execute("SELECT symbol FROM symbols ORDER BY symbol").fetchall()
    return [str(r[0]) for r in rows]


def _clear_existing(conn: sqlite3.Connection, symbol: str) -> None:
    norm = "".join(ch for ch in symbol.upper() if ch.isalnum())
    conn.execute(
        """
        DELETE FROM trades
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND LOWER(version) = ?
          AND mode IN ('backtest', 'paper')
        """,
        (norm, VERSION),
    )
    conn.execute(
        """
        DELETE FROM backtest_results
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND notes LIKE ?
        """,
        (norm, f"%{VERSION_NOTE}%"),
    )
    conn.execute(
        """
        DELETE FROM paper_trading_results
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND notes LIKE ?
        """,
        (norm, f"%{VERSION_NOTE}%"),
    )


def _build_rows(symbol: str, trades, df) -> list[tuple]:
    rows: list[tuple] = []
    if trades.empty:
        return rows

    for _, trade in trades.iterrows():
        entry_time = _timestamp_at(df, trade.get("entry_idx"))
        exit_time = _timestamp_at(df, trade.get("exit_idx"))
        dollar_pnl = float(trade.get("pnl", trade.get("dollar_pnl", 0.0)) or 0.0)
        equity = float(trade.get("equity", 0.0) or 0.0)
        beginning_equity = equity - dollar_pnl
        pnl_pct = (dollar_pnl / beginning_equity * 100.0) if beginning_equity else None
        rows.append(
            (
                symbol,
                VERSION,
                entry_time,
                exit_time,
                "short",
                float(trade.get("entry", 0.0) or 0.0),
                float(trade.get("exit", 0.0) or 0.0),
                _result_label(trade.get("exit_type")),
                pnl_pct,
                dollar_pnl,
                equity,
            )
        )
    return rows


def _insert_trades(conn: sqlite3.Connection, mode: str, rows: list[tuple]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO trades (
            symbol, version, mode, entry_time, exit_time, direction,
            entry_price, exit_price, result, pnl_pct, dollar_pnl, equity
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(r[0], r[1], mode, r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]) for r in rows],
    )


def _insert_summary(conn: sqlite3.Connection, table: str, symbol: str, metrics: dict, notes: str) -> None:
    conn.execute(
        f"INSERT INTO {table} (symbol, metrics, notes) VALUES (?, ?, ?)",
        (symbol, json.dumps(metrics), notes),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate aligned v1 backtest/paper datasets.")
    parser.add_argument("--symbol", help="Optional symbol (e.g. BTC/USD). If omitted, run for all symbols.")
    args = parser.parse_args()

    db = Path(DB_PATH)
    if not db.exists():
        print(f"ERROR: DB not found: {db}", file=sys.stderr)
        return 2

    backup = _backup_db(db)
    print(f"Backup created: {backup.name}")

    conn = sqlite3.connect(str(db), timeout=60)
    conn.execute("PRAGMA journal_mode=DELETE")

    try:
        symbols = _load_symbols(conn, args.symbol)
        if not symbols:
            print("No symbols found.")
            return 0

        for symbol in symbols:
            print(f"\n[RUN] {symbol} {VERSION}")
            _clear_existing(conn, symbol)
            df = fetch_ohlcv(symbol)
            trades = run_backtest(df, VERSION)
            rows = _build_rows(symbol, trades, df)

            _insert_trades(conn, "backtest", rows)
            _insert_trades(conn, "paper", rows)

            metrics = _metrics_for_trades(symbol, VERSION, trades, df)
            _insert_summary(conn, "backtest_results", symbol, metrics, f"{VERSION_NOTE} backtest summary")
            _insert_summary(conn, "paper_trading_results", symbol, metrics, f"{VERSION_NOTE} paper trading summary")

            print(f"  bars={len(df):,} trades={len(rows)}")

        conn.commit()
        print("\nAligned v1 backtest/paper datasets regenerated.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
