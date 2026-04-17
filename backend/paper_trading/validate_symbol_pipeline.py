
"""
DEPRECATED: This script used SQLite (tradingcopilot.db) and is no longer supported.
Please use the MariaDB-based tools and workflows for pipeline validation.
"""

import sys
print("[DEPRECATED] validate_symbol_pipeline.py is no longer supported. Use MariaDB-based validation.", file=sys.stderr)
sys.exit(1)

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from backtest_backtrader_alpaca import VERSION_MAP  # noqa: E402

DEFAULT_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"


def _normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


@dataclass
class VersionCheck:
    version: str
    backtest_trades: int
    paper_trades: int
    backtest_summaries: int
    paper_summaries: int
    realtime_rows: int
    realtime_summaries: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that a symbol has complete backtest/paper/realtime coverage for each version."
    )
    parser.add_argument("--symbol", required=True, help="Symbol to validate, e.g. BTC/USDT")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to tradingcopilot.db")
    parser.add_argument(
        "--version",
        action="append",
        choices=list(VERSION_MAP.keys()),
        help="Optional version filter (repeat flag for multiple). Defaults to v1-v6.",
    )
    parser.add_argument(
        "--skip-realtime",
        action="store_true",
        help="Skip realtime checks (realtime_paper_log and realtime summaries).",
    )
    return parser.parse_args()


def _symbol_exists(conn: sqlite3.Connection, symbol: str) -> bool:
    norm = _normalize_symbol(symbol)
    row = conn.execute(
        """
        SELECT 1
        FROM symbols
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
        LIMIT 1
        """,
        (norm,),
    ).fetchone()
    return bool(row)


def _count_trades(conn: sqlite3.Connection, symbol: str, version: str, mode: str) -> int:
    norm = _normalize_symbol(symbol)
    row = conn.execute(
        """
        SELECT COUNT(1)
        FROM trades
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND LOWER(version) = ?
          AND mode = ?
        """,
        (norm, version, mode),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _count_summaries(conn: sqlite3.Connection, table: str, symbol: str, note_fragment: str) -> int:
    norm = _normalize_symbol(symbol)
    row = conn.execute(
        f"""
        SELECT COUNT(1)
        FROM {table}
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND notes LIKE ?
        """,
        (norm, f"%{note_fragment}%"),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _count_realtime_rows(conn: sqlite3.Connection, symbol: str, version: str) -> int:
    # Table may not exist if realtime paper has never been run in this DB.
    try:
        norm = _normalize_symbol(symbol)
        row = conn.execute(
            """
            SELECT COUNT(1)
            FROM realtime_paper_log
            WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
              AND LOWER(version) = ?
            """,
            (norm, version),
        ).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.OperationalError:
        return 0


def _check_version(conn: sqlite3.Connection, symbol: str, version: str, include_realtime: bool) -> VersionCheck:
    version_note = VERSION_MAP[version]
    backtest_trades = _count_trades(conn, symbol, version, "backtest")
    paper_trades = _count_trades(conn, symbol, version, "paper")
    backtest_summaries = _count_summaries(conn, "backtest_results", symbol, f"{version_note} backtest summary")
    paper_summaries = _count_summaries(conn, "paper_trading_results", symbol, f"{version_note} paper trading summary")

    realtime_rows = 0
    realtime_summaries = 0
    if include_realtime:
        realtime_rows = _count_realtime_rows(conn, symbol, version)
        realtime_summaries = _count_summaries(
            conn,
            "paper_trading_results",
            symbol,
            f"{version_note} realtime alpaca summary",
        )

    return VersionCheck(
        version=version,
        backtest_trades=backtest_trades,
        paper_trades=paper_trades,
        backtest_summaries=backtest_summaries,
        paper_summaries=paper_summaries,
        realtime_rows=realtime_rows,
        realtime_summaries=realtime_summaries,
    )


def main() -> int:
    args = _parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 2

    versions = [v.strip().lower() for v in (args.version or []) if v and v.strip()]
    if not versions:
        versions = list(VERSION_MAP.keys())

    conn = sqlite3.connect(str(db_path))
    try:
        if not _symbol_exists(conn, args.symbol):
            print(f"ERROR: Symbol not found in symbols table: {args.symbol}", file=sys.stderr)
            return 1

        include_realtime = not args.skip_realtime
        checks = [_check_version(conn, args.symbol, version, include_realtime) for version in versions]

        print(f"Symbol pipeline report: {args.symbol}")
        print(f"Versions: {', '.join(versions)}")
        if args.skip_realtime:
            print("Realtime checks: skipped")

        failures: list[str] = []
        for c in checks:
            print(
                f"[{c.version}] bt_trades={c.backtest_trades} paper_trades={c.paper_trades} "
                f"bt_summary={c.backtest_summaries} paper_summary={c.paper_summaries} "
                f"rt_rows={c.realtime_rows} rt_summary={c.realtime_summaries}"
            )

            if c.backtest_trades <= 0:
                failures.append(f"{c.version}: missing backtest trades")
            if c.paper_trades <= 0:
                failures.append(f"{c.version}: missing simulated paper trades")
            if c.backtest_trades != c.paper_trades:
                failures.append(
                    f"{c.version}: trade count mismatch backtest={c.backtest_trades} paper={c.paper_trades}"
                )
            if c.backtest_summaries <= 0:
                failures.append(f"{c.version}: missing backtest summary row")
            if c.paper_summaries <= 0:
                failures.append(f"{c.version}: missing paper summary row")

            if include_realtime:
                if c.realtime_rows <= 0:
                    failures.append(f"{c.version}: missing realtime paper log rows")
                if c.realtime_summaries <= 0:
                    failures.append(f"{c.version}: missing realtime summary row")

        if failures:
            print("\nFAILED:", file=sys.stderr)
            for msg in failures:
                print(f"  - {msg}", file=sys.stderr)
            return 1

        print("\nPASSED: symbol is complete for the requested pipeline stages.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
