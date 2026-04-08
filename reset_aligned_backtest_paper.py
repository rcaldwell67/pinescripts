"""Regenerate aligned backtest/paper datasets in tradingcopilot.db for v1-v6.

This script runs the selected version backtest simulation once per symbol and
writes identical trade rows into both mode='backtest' and mode='paper' so
parity validation can operate on aligned inputs.

Usage examples:
    python reset_aligned_backtest_paper.py --version v1
    python reset_aligned_backtest_paper.py --version v3 --version v4 --symbol BTC/USD
    python reset_aligned_backtest_paper.py --all-versions
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "strategy_generator"))

from backtest_backtrader_alpaca import DB_PATH, VERSION_MAP, fetch_ohlcv, run_backtest  # noqa: E402
from paper_trading.paper_trade_backtrader_alpaca import _metrics_for_trades, _result_label, _timestamp_at  # noqa: E402

ALL_VERSIONS = tuple(VERSION_MAP.keys())


def _backup_db(db_path: Path, versions: list[str]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "_".join(versions)
    backup = db_path.with_name(f"{db_path.stem}.pre_align_{suffix}_{stamp}{db_path.suffix}")
    backup.write_bytes(db_path.read_bytes())
    return backup


def _load_symbols(conn: sqlite3.Connection, symbol: str | None) -> list[str]:
    if symbol:
        return [symbol.strip()]
    rows = conn.execute("SELECT symbol FROM symbols ORDER BY symbol").fetchall()
    return [str(r[0]) for r in rows]


def _clear_existing(conn: sqlite3.Connection, symbol: str, version: str, version_note: str) -> None:
    norm = "".join(ch for ch in symbol.upper() if ch.isalnum())
    conn.execute(
        """
        DELETE FROM trades
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND LOWER(version) = ?
          AND mode IN ('backtest', 'paper')
        """,
        (norm, version),
    )
    conn.execute(
        """
        DELETE FROM backtest_results
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND notes LIKE ?
        """,
        (norm, f"%{version_note}%"),
    )
    conn.execute(
        """
        DELETE FROM paper_trading_results
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND notes LIKE ?
        """,
        (norm, f"%{version_note}%"),
    )


def _build_rows(symbol: str, version: str, trades, df) -> list[tuple]:
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

        # v1 backtest rows historically omit `side`; newer versions provide it.
        side = str(trade.get("side", "") or "").lower().strip()
        if side in ("long", "short"):
            direction = side
        else:
            direction = "short"

        rows.append(
            (
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
            )
        )
    return rows


def _insert_trades(conn: sqlite3.Connection, mode: str, rows: list[tuple]) -> None:
    if not rows:
        return
    source = "simulation" if mode == "paper" else None
    conn.executemany(
        """
        INSERT INTO trades (
            symbol, version, mode, entry_time, exit_time, direction,
            entry_price, exit_price, result, pnl_pct, dollar_pnl, equity, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(r[0], r[1], mode, r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], source) for r in rows],
    )


def _insert_summary(conn: sqlite3.Connection, table: str, symbol: str, metrics: dict, notes: str) -> None:
    conn.execute(
        f"INSERT INTO {table} (symbol, metrics, notes) VALUES (?, ?, ?)",
        (symbol, json.dumps(metrics), notes),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate aligned backtest/paper datasets for v1-v6.")
    parser.add_argument("--symbol", help="Optional symbol (e.g. BTC/USD). If omitted, run for all symbols.")
    parser.add_argument(
        "--version",
        action="append",
        choices=list(ALL_VERSIONS),
        help="Strategy version to regenerate. Repeat the flag to run multiple versions.",
    )
    parser.add_argument(
        "--all-versions",
        action="store_true",
        help="Regenerate all supported versions (v1-v6).",
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
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    versions = [v.strip().lower() for v in (args.version or []) if v and v.strip()]
    if args.all_versions or not versions:
        versions = list(ALL_VERSIONS)

    db = Path(DB_PATH)
    if not db.exists():
        print(f"ERROR: DB not found: {db}", file=sys.stderr)
        return 2

    backup = _backup_db(db, versions)
    print(f"Backup created: {backup.name}")

    conn = sqlite3.connect(str(db), timeout=60)
    conn.execute("PRAGMA journal_mode=DELETE")

    try:
        symbols = _load_symbols(conn, args.symbol)
        if not symbols:
            print("No symbols found.")
            return 0

        for version in versions:
            version_note = VERSION_MAP[version]
            for symbol in symbols:
                print(f"\n[RUN] {symbol} {version}")
                _clear_existing(conn, symbol, version, version_note)
                df = fetch_ohlcv(
                    symbol,
                    prefer_realtime_bar=args.prefer_realtime_data,
                    alpaca_only=args.realtime_only_data,
                    data_scope=args.data_scope,
                )
                trades = run_backtest(df, version, symbol=symbol)
                rows = _build_rows(symbol, version, trades, df)

                _insert_trades(conn, "backtest", rows)
                _insert_trades(conn, "paper", rows)

                metrics = _metrics_for_trades(symbol, version, trades, df)
                _insert_summary(conn, "backtest_results", symbol, metrics, f"{version_note} backtest summary")
                _insert_summary(conn, "paper_trading_results", symbol, metrics, f"{version_note} paper trading summary")

                print(f"  bars={len(df):,} trades={len(rows)}")

        conn.commit()
        print("\nAligned backtest/paper datasets regenerated.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
