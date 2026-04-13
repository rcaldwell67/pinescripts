"""
Export realtime_paper_trading_results.json from realtime_paper_log table in tradingcopilot.db.

Reads the 'realtime_paper_log' table and writes docs/data/realtime_paper_trading_results.json
with the latest equity/status per symbol/version.

Usage:
    python backend/data/export_realtime_paper_trading_results.py
"""

from __future__ import annotations
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"
DEFAULT_OUT = REPO_ROOT / "docs" / "data" / "realtime_paper_trading_results.json"

def export(db_path: Path = DEFAULT_DB, out_path: Path = DEFAULT_OUT) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT symbol, version, status, detail, equity, logged_at
            FROM realtime_paper_log
            WHERE symbol != '__scheduler__'
            ORDER BY symbol, version, logged_at DESC, id DESC
            """,
        ).fetchall()
    finally:
        conn.close()

    result: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        symbol = str(row["symbol"])
        version = str(row["version"])
        key = (symbol, version)
        if key in seen:
            continue
        seen.add(key)
        result[symbol].append({
            "symbol": symbol,
            "version": version,
            "status": row["status"],
            "detail": row["detail"],
            "equity": row["equity"],
            "logged_at": row["logged_at"],
        })

    # Sort each symbol's list by version for consistent ordering
    for sym in result:
        result[sym].sort(key=lambda x: str(x.get("version", "")))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dict(result), indent=2), encoding="utf-8")
    total = sum(len(v) for v in result.values())
    print(f"Wrote {out_path}  ({len(result)} symbols, {total} rows)")

if __name__ == "__main__":
    export()
