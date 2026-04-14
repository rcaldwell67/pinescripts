"""
Validate live fill/trade consistency in tradingcopilot.db.

Checks per symbol:
- Number of sell/buy fill events from live_fill_events
- Number of open/closed live trades in trades(mode='live') for a version
- Expected open and closed trade counts derived from fill-side counts

Usage:
    python backend/live_trading/verify_live_consistency.py --version v1
    python backend/live_trading/verify_live_consistency.py --version v6 --symbol CLM
"""

from __future__ import annotations


import argparse
import sqlite3
import sys
import logging
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_PATH = REPO_ROOT / "backend" / "live_consistency_error.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("live_consistency")


@dataclass
class SymbolConsistencyResult:
    symbol: str
    sell_fills: int
    buy_fills: int
    open_trades: int
    closed_trades: int
    mismatches: list[str]


def _normalized_symbol_key(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def _all_symbols(conn: sqlite3.Connection, version: str) -> list[str]:
    stmt = conn.execute(
        """
        SELECT DISTINCT symbol
        FROM trades
        WHERE mode = 'live' AND LOWER(version) = ?
        ORDER BY symbol
        """,
        (version.lower(),),
    )
    symbols = [str(row[0]) for row in stmt.fetchall()]
    if symbols:
        return symbols

    # Fall back to fill table symbols when trades are empty.
    try:
        stmt = conn.execute("SELECT DISTINCT symbol FROM live_fill_events ORDER BY symbol")
        return [str(row[0]) for row in stmt.fetchall()]
    except sqlite3.OperationalError:
        return []


def _fill_counts(conn: sqlite3.Connection, symbol: str) -> tuple[int, int]:
    norm = _normalized_symbol_key(symbol)
    try:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN LOWER(side) = 'sell' THEN 1 ELSE 0 END) AS sell_count,
                SUM(CASE WHEN LOWER(side) = 'buy' THEN 1 ELSE 0 END)  AS buy_count
            FROM live_fill_events
            WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
            """,
            (norm,),
        ).fetchone()
    except sqlite3.OperationalError:
        return 0, 0
    sell_count = int(row[0] or 0) if row else 0
    buy_count = int(row[1] or 0) if row else 0
    return sell_count, buy_count


def _trade_counts(conn: sqlite3.Connection, symbol: str, version: str) -> tuple[int, int]:
    norm = _normalized_symbol_key(symbol)
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN exit_time IS NULL THEN 1 ELSE 0 END) AS open_count,
            SUM(CASE WHEN exit_time IS NOT NULL THEN 1 ELSE 0 END) AS closed_count
        FROM trades
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND mode = 'live'
          AND LOWER(version) = ?
        """,
        (norm, version.lower()),
    ).fetchone()
    open_count = int(row[0] or 0) if row else 0
    closed_count = int(row[1] or 0) if row else 0
    return open_count, closed_count


def _compare_symbol(conn: sqlite3.Connection, symbol: str, version: str) -> SymbolConsistencyResult:
    sell_fills, buy_fills = _fill_counts(conn, symbol)
    open_trades, closed_trades = _trade_counts(conn, symbol, version)

    expected_open = max(0, sell_fills - buy_fills)
    expected_closed = min(sell_fills, buy_fills)
    mismatches: list[str] = []

    if open_trades != expected_open:
        mismatches.append(
            f"open_trades mismatch: trades={open_trades} expected={expected_open} (sell_fills={sell_fills}, buy_fills={buy_fills})"
        )
    if closed_trades != expected_closed:
        mismatches.append(
            f"closed_trades mismatch: trades={closed_trades} expected={expected_closed} (sell_fills={sell_fills}, buy_fills={buy_fills})"
        )
    if buy_fills > sell_fills:
        mismatches.append(
            f"buy_fills exceeds sell_fills: sells={sell_fills}, buys={buy_fills}"
        )

    return SymbolConsistencyResult(
        symbol=symbol,
        sell_fills=sell_fills,
        buy_fills=buy_fills,
        open_trades=open_trades,
        closed_trades=closed_trades,
        mismatches=mismatches,
    )


def _print_report(results: list[SymbolConsistencyResult]) -> None:
    print("\n=== Live Fill/Trade Consistency Report ===")
    for res in results:
        status = "PASS" if not res.mismatches else "FAIL"
        print(
            f"[{status}] {res.symbol} | fills(sell/buy)={res.sell_fills}/{res.buy_fills} "
            f"trades(open/closed)={res.open_trades}/{res.closed_trades}"
        )
        for msg in res.mismatches:
            print(f"  - {msg}")



def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live fill/trade consistency.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to tradingcopilot.db")
    parser.add_argument("--version", default="v1", help="Version to validate against live trades (v1-v6)")
    parser.add_argument("--symbol", action="append", help="Optional symbol filter; can be passed multiple times")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        logger.error(f"DB not found: {db_path}")
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    try:
        symbols = args.symbol if args.symbol else _all_symbols(conn, args.version)
        if not symbols:
            logger.info("No live symbols found for consistency check.")
            print("No live symbols found for consistency check.")
            return 0

        results = []
        for symbol in symbols:
            try:
                results.append(_compare_symbol(conn, symbol, args.version))
            except Exception as e:
                logger.error(f"Error comparing symbol {symbol}: {e}", exc_info=True)
        _print_report(results)

        failures = [r for r in results if r.mismatches]
        if failures:
            logger.warning(f"Consistency FAILED for {len(failures)} symbol(s).")
            print(f"\nConsistency FAILED for {len(failures)} symbol(s).", file=sys.stderr)
            return 1

        logger.info("Consistency PASSED for all compared symbols.")
        print("\nConsistency PASSED for all compared symbols.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())