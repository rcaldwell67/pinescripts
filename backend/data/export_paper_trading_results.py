"""Export paper_trading_results.json from simulation summary rows in tradingcopilot.db.

Reads the 'paper_trading_results' table (notes LIKE '%paper trading summary%')
and writes docs/data/paper_trading_results.json in the same grouped format as
backtest_results.json {symbol: [{...}]} so the dashboard comparison view works
against aligned data.

Usage:
    python backend/data/export_paper_trading_results.py
"""

from __future__ import annotations
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"
DEFAULT_OUT = REPO_ROOT / "docs" / "data" / "paper_trading_results.json"


def export(db_path: Path = DEFAULT_DB, out_path: Path = DEFAULT_OUT) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT symbol, notes, metrics, COALESCE(timestamp, '') AS ts
            FROM paper_trading_results
            WHERE lower(notes) LIKE '%paper trading summary%'
            ORDER BY symbol, COALESCE(timestamp, '') DESC, id DESC
            """,
        ).fetchall()
    finally:
        conn.close()

    result: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        symbol = str(row["symbol"])
        try:
            m = json.loads(row["metrics"] or "{}")
        except Exception:
            m = {}
        if not m:
            continue
        # Resolve version from metrics or notes
        ver = str(m.get("version", "") or "").strip().lower()
        if not ver:
            match = re.search(r'\bv([1-6])\b', str(row["notes"] or ""), re.IGNORECASE)
            ver = match.group(0).lower() if match else "v1"
        key = (symbol, ver)
        if key in seen:
            continue
        seen.add(key)
        result[symbol].append(m)

    # Sort each symbol's list by version for consistent ordering
    for sym in result:
        result[sym].sort(key=lambda x: str(x.get("version", "")))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dict(result), indent=2), encoding="utf-8")
    total = sum(len(v) for v in result.values())
    print(f"Wrote {out_path}  ({len(result)} symbols, {total} rows)")


if __name__ == "__main__":
    export()
