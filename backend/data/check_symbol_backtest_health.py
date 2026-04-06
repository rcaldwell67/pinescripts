"""Return failing backtest versions for a symbol based on quality rules.

Rules:
- Missing summary row => fail
- total_trades <= 0 => fail
- net_return_pct < 0 => fail
- v1/v2 net_return_pct < 20 => fail (guideline floor)

Prints failing versions as space-separated values (e.g. "v3 v4").
Prints empty line when all versions pass.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check per-version backtest health for a symbol")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--db", default="docs/data/tradingcopilot.db")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        print("v1 v2 v3 v4 v5 v6")
        return 0

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """
        SELECT timestamp, metrics, notes
        FROM backtest_results
        WHERE symbol = ?
        ORDER BY timestamp DESC
        """,
        (args.symbol,),
    ).fetchall()
    conn.close()

    latest: dict[str, dict] = {}
    for _, metrics_json, notes in rows:
        try:
            metrics = json.loads(metrics_json or "{}")
        except Exception:
            metrics = {}
        ver = str(metrics.get("version") or "").strip().lower()
        if not ver:
            m = re.search(r"\b(v[1-6])\b", str(notes or ""), re.I)
            ver = m.group(1).lower() if m else ""
        if ver and ver not in latest:
            latest[ver] = metrics

    failed: list[str] = []
    for ver in ["v1", "v2", "v3", "v4", "v5", "v6"]:
        m = latest.get(ver)
        if not m:
            failed.append(ver)
            continue

        trades = int(m.get("total_trades") or 0)
        net = float(m.get("net_return_pct") or 0.0)
        if trades <= 0 or net < 0.0:
            failed.append(ver)
            continue

        if ver in {"v1", "v2"} and net < 20.0:
            failed.append(ver)

    print(" ".join(failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
