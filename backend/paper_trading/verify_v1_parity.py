
"""
DEPRECATED: This script used SQLite (tradingcopilot.db) and is no longer supported.
Please use the MariaDB-based tools and workflows for parity validation.
"""

import sys
print("[DEPRECATED] verify_v1_parity.py is no longer supported. Use MariaDB-based validation.", file=sys.stderr)
sys.exit(1)

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"


@dataclass
class TradeRow:
    entry_time: str | None
    exit_time: str | None
    direction: str | None
    entry_price: float | None
    exit_price: float | None
    result: str | None
    pnl_pct: float | None
    dollar_pnl: float | None
    equity: float | None


@dataclass
class SymbolParityResult:
    symbol: str
    backtest_count: int
    paper_count: int
    matched_rows: int
    mismatches: list[str]


def _normalized_symbol_key(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _rows_for_mode(conn: sqlite3.Connection, symbol: str, version: str, mode: str) -> list[TradeRow]:
    norm_key = _normalized_symbol_key(symbol)
    stmt = conn.execute(
        """
        SELECT entry_time, exit_time, direction, entry_price, exit_price, result,
               pnl_pct, dollar_pnl, equity
        FROM trades
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND LOWER(version) = ?
          AND mode = ?
        ORDER BY entry_time, id
        """,
        (norm_key, version.lower(), mode),
    )
    out: list[TradeRow] = []
    for row in stmt.fetchall():
        out.append(
            TradeRow(
                entry_time=_to_text(row[0]),
                exit_time=_to_text(row[1]),
                direction=_to_text(row[2]),
                entry_price=_to_float(row[3]),
                exit_price=_to_float(row[4]),
                result=_to_text(row[5]),
                pnl_pct=_to_float(row[6]),
                dollar_pnl=_to_float(row[7]),
                equity=_to_float(row[8]),
            )
        )
    return out


def _all_symbols(conn: sqlite3.Connection, version: str) -> list[str]:
    stmt = conn.execute(
        """
        SELECT DISTINCT symbol
        FROM trades
        WHERE LOWER(version) = ?
          AND mode IN ('backtest', 'paper')
        ORDER BY symbol
        """,
        (version.lower(),),
    )
    raw_symbols = [str(row[0]) for row in stmt.fetchall()]
    by_norm: dict[str, list[str]] = {}
    for sym in raw_symbols:
        by_norm.setdefault(_normalized_symbol_key(sym), []).append(sym)

    selected: list[str] = []
    for group in by_norm.values():
        # Prefer slash-form symbols for display consistency with the dashboard.
        preferred = sorted(group, key=lambda s: ("/" not in s, s))[0]
        selected.append(preferred)
    return sorted(selected)


def _cmp_text(left: str | None, right: str | None) -> bool:
    if left is None and right is None:
        return True
    return (left or "").strip().lower() == (right or "").strip().lower()


def _cmp_float(left: float | None, right: float | None, tol: float) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return abs(left - right) <= tol


def _compare_symbol(
    symbol: str,
    backtest_rows: list[TradeRow],
    paper_rows: list[TradeRow],
    *,
    price_tol: float,
    pnl_tol: float,
    max_row_diffs: int,
) -> SymbolParityResult:
    mismatches: list[str] = []
    n = min(len(backtest_rows), len(paper_rows))

    if len(backtest_rows) != len(paper_rows):
        mismatches.append(
            f"row_count mismatch: backtest={len(backtest_rows)} paper={len(paper_rows)}"
        )

    for i in range(n):
        b = backtest_rows[i]
        p = paper_rows[i]
        row_notes: list[str] = []

        if not _cmp_text(b.entry_time, p.entry_time):
            row_notes.append(f"entry_time bt={b.entry_time} paper={p.entry_time}")
        if not _cmp_text(b.exit_time, p.exit_time):
            row_notes.append(f"exit_time bt={b.exit_time} paper={p.exit_time}")
        if not _cmp_text(b.direction, p.direction):
            row_notes.append(f"direction bt={b.direction} paper={p.direction}")
        if not _cmp_text(b.result, p.result):
            row_notes.append(f"result bt={b.result} paper={p.result}")

        if not _cmp_float(b.entry_price, p.entry_price, price_tol):
            row_notes.append(f"entry_price bt={b.entry_price} paper={p.entry_price}")
        if not _cmp_float(b.exit_price, p.exit_price, price_tol):
            row_notes.append(f"exit_price bt={b.exit_price} paper={p.exit_price}")
        if not _cmp_float(b.pnl_pct, p.pnl_pct, pnl_tol):
            row_notes.append(f"pnl_pct bt={b.pnl_pct} paper={p.pnl_pct}")
        if not _cmp_float(b.dollar_pnl, p.dollar_pnl, pnl_tol):
            row_notes.append(f"dollar_pnl bt={b.dollar_pnl} paper={p.dollar_pnl}")
        if not _cmp_float(b.equity, p.equity, pnl_tol):
            row_notes.append(f"equity bt={b.equity} paper={p.equity}")

        if row_notes:
            mismatches.append(f"row {i + 1}: " + "; ".join(row_notes))
            if len(mismatches) >= max_row_diffs:
                mismatches.append(f"... truncated after {max_row_diffs} differences")
                break

    return SymbolParityResult(
        symbol=symbol,
        backtest_count=len(backtest_rows),
        paper_count=len(paper_rows),
        matched_rows=n,
        mismatches=mismatches,
    )


def _print_report(results: Iterable[SymbolParityResult]) -> None:
    print("\n=== v1 Backtest vs Paper Parity Report ===")
    for res in results:
        status = "PASS" if not res.mismatches else "FAIL"
        print(
            f"[{status}] {res.symbol} | backtest={res.backtest_count} "
            f"paper={res.paper_count} compared={res.matched_rows}"
        )
        if res.mismatches:
            for msg in res.mismatches:
                print(f"  - {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate v1 parity between backtest and paper trade rows.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to tradingcopilot.db")
    parser.add_argument("--version", default="v1", help="Strategy version to compare (default: v1)")
    parser.add_argument("--symbol", action="append", help="Optional symbol filter; can be passed multiple times")
    parser.add_argument("--price-tol", type=float, default=1e-6, help="Absolute tolerance for price comparisons")
    parser.add_argument("--pnl-tol", type=float, default=1e-6, help="Absolute tolerance for pnl/equity comparisons")
    parser.add_argument("--max-row-diffs", type=int, default=25, help="Max per-symbol mismatch lines to print")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    try:
        symbols = args.symbol if args.symbol else _all_symbols(conn, args.version)
        if not symbols:
            print("No symbols found for comparison.")
            return 0

        results: list[SymbolParityResult] = []
        for symbol in symbols:
            bt = _rows_for_mode(conn, symbol, args.version, "backtest")
            pp = _rows_for_mode(conn, symbol, args.version, "paper")
            results.append(
                _compare_symbol(
                    symbol,
                    bt,
                    pp,
                    price_tol=args.price_tol,
                    pnl_tol=args.pnl_tol,
                    max_row_diffs=args.max_row_diffs,
                )
            )

        _print_report(results)
        failures = [r for r in results if r.mismatches]
        if failures:
            print(f"\nParity FAILED for {len(failures)} symbol(s).", file=sys.stderr)
            return 1

        print("\nParity PASSED for all compared symbols.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
