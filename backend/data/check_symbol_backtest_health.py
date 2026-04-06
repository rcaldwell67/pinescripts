"""Return failing backtest versions for a symbol based on guideline health rules.

Guideline thresholds and policies are sourced from backend/config/guideline_policy.py
to ensure consistency with dashboard audit logic and other backend checks.

Prints failing versions as space-separated values (e.g. "v3 v4").
Prints empty line when all versions pass.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

# Import centralized guideline policy
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "config"))
from guideline_policy import DEFAULT_THRESHOLDS, normalize_symbol, get_override, evaluate_backtest_guideline

VERSION_KEYS = ["v1", "v2", "v3", "v4", "v5", "v6"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check per-version backtest health for a symbol")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--db", default="docs/data/tradingcopilot.db")
    return parser.parse_args()


def _norm_symbol(symbol: str) -> str:
    """Deprecated: use normalize_symbol from guideline_policy instead."""
    return normalize_symbol(symbol)


def _parse_version(metrics: dict, notes: str) -> str:
    ver = str(metrics.get("version") or "").strip().lower()
    if ver in VERSION_KEYS:
        return ver
    m = re.search(r"\b(v[1-6])\b", str(notes or ""), re.I)
    return m.group(1).lower() if m else ""


def _to_float(value: object) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


def _to_int(value: object) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _trade_metrics(conn: sqlite3.Connection, symbol: str, version: str) -> tuple[int, float | None, float | None]:
    rows = conn.execute(
        """
        SELECT dollar_pnl, equity
        FROM trades
        WHERE symbol = ? AND LOWER(version) = ? AND mode = 'backtest'
        ORDER BY exit_time ASC, id ASC
        """,
        (symbol, version),
    ).fetchall()
    if not rows:
        return 0, None, None

    pnl = [float(r[0] or 0.0) for r in rows]
    eq = [float(r[1] or 0.0) for r in rows]
    trades = len(rows)

    win_rate = (sum(1 for x in pnl if x > 0) / trades * 100.0) if trades else None

    peak = float("-inf")
    max_dd = 0.0
    for e in eq:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak * 100.0)

    return trades, win_rate, max_dd


def main() -> int:
    args = _parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        print(" ".join(VERSION_KEYS))
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

    latest: dict[str, dict] = {}
    for _, metrics_json, notes in rows:
        try:
            metrics = json.loads(metrics_json or "{}")
        except Exception:
            metrics = {}

        ver = _parse_version(metrics, str(notes or ""))
        if ver and ver not in latest:
            latest[ver] = metrics

    failed: list[str] = []
    for ver in VERSION_KEYS:
        metrics = latest.get(ver)
        if not metrics:
            failed.append(ver)
            continue

        trades = _to_int(metrics.get("total_trades"))
        win_rate = _to_float(metrics.get("win_rate"))
        if win_rate is None:
            win_rate = _to_float(metrics.get("win_rate_pct"))

        net_return = _to_float(metrics.get("net_return_pct"))

        max_drawdown = _to_float(metrics.get("max_drawdown_pct"))
        if max_drawdown is None:
            dd_abs = _to_float(metrics.get("max_drawdown"))
            begin_eq = _to_float(metrics.get("beginning_equity"))
            if dd_abs is not None and begin_eq and begin_eq > 0:
                max_drawdown = dd_abs / begin_eq * 100.0

        # Fall back to trade-derived metrics when summary fields are missing.
        trade_count, trade_win_rate, trade_max_dd = _trade_metrics(conn, args.symbol, ver)
        if trades is None:
            trades = trade_count
        if win_rate is None:
            win_rate = trade_win_rate
        if max_drawdown is None:
            max_drawdown = trade_max_dd

        if not evaluate_backtest_guideline(args.symbol, ver, trades, win_rate, net_return, max_drawdown)[0]:
            failed.append(ver)

    conn.close()
    print(" ".join(failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
