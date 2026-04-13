"""Export a lightweight dashboard snapshot for the React monitor.

Reads trading data from docs/data/tradingcopilot.db and writes JSON to:
- docs/data/dashboard_snapshot.json
- frontend-react/public/data/dashboard_snapshot.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "frontend-react" / "public" / "data" / "tradingcopilot.db"
DEFAULT_OUTPUTS = [
    REPO_ROOT / "docs" / "data" / "dashboard_snapshot.json",
    REPO_ROOT / "frontend-react" / "public" / "data" / "dashboard_snapshot.json",
]


def _norm_symbol(symbol: str) -> str:
    return "".join(ch for ch in str(symbol).upper() if ch.isalnum())


def _asset_class(symbol: str) -> str:
    s = str(symbol).upper()
    if "/" in s or s.endswith("USD"):
        return "crypto"
    return "etf"


def _parse_metrics(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rows(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    cur = conn.execute(query, params)
    return cur.fetchall()


def _load_symbols(conn: sqlite3.Connection) -> list[dict[str, str]]:
    data: list[dict[str, str]] = []
    for row in _rows(conn, "SELECT symbol FROM symbols ORDER BY symbol"):
        symbol = str(row["symbol"])
        data.append({
            "symbol": symbol,
            "symbol_key": _norm_symbol(symbol),
            "asset_class": _asset_class(symbol),
        })
    return data


def _latest_account(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(
        conn,
        """
        SELECT account_mode, beginning_balance, current_balance, buying_power, cash, updated_at
        FROM Account_Info
        ORDER BY COALESCE(updated_at, '') DESC, rowid DESC
        LIMIT 1
        """,
    )
    if not rows:
        return {}
    row = rows[0]
    return {
        "mode": row["account_mode"],
        "beginning_balance": row["beginning_balance"],
        "current_balance": row["current_balance"],
        "buying_power": row["buying_power"],
        "cash": row["cash"],
        "updated_at": row["updated_at"],
    }


def _latest_results(conn: sqlite3.Connection, table: str, mode_name: str) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        f"""
        SELECT r.symbol, r.timestamp, r.current_equity, r.metrics
        FROM {table} r
        JOIN (
          SELECT symbol, MAX(COALESCE(timestamp, '')) AS max_ts
          FROM {table}
          GROUP BY symbol
        ) latest
          ON latest.symbol = r.symbol
         AND COALESCE(r.timestamp, '') = latest.max_ts
        ORDER BY r.symbol
        """,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        metrics = _parse_metrics(row["metrics"])
        # Compute max_drawdown_pct if missing and possible
        max_drawdown_pct = metrics.get("max_drawdown_pct")
        if max_drawdown_pct is None:
            max_drawdown = metrics.get("max_drawdown")
            beginning_equity = metrics.get("beginning_equity")
            if max_drawdown is not None and beginning_equity:
                try:
                    max_drawdown_pct = float(max_drawdown) / float(beginning_equity) * 100.0
                except Exception:
                    max_drawdown_pct = None
        out.append(
            {
                "mode": mode_name,
                "symbol": row["symbol"],
                "symbol_key": _norm_symbol(row["symbol"]),
                "timestamp": row["timestamp"],
                "current_equity": row["current_equity"],
                "net_return_pct": metrics.get("net_return_pct"),
                "win_rate": metrics.get("win_rate") or metrics.get("win_rate_pct"),
                "max_drawdown_pct": max_drawdown_pct,
                "total_trades": metrics.get("total_trades") or metrics.get("trades"),
            }
        )
    return out


def _latest_trades(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT symbol, version, mode, direction, entry_time, exit_time, entry_price, exit_price,
               result, pnl_pct, dollar_pnl, equity, source
        FROM trades
        ORDER BY datetime(COALESCE(exit_time, entry_time)) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "symbol": row["symbol"],
                "symbol_key": _norm_symbol(row["symbol"]),
                "asset_class": _asset_class(row["symbol"]),
                "version": row["version"],
                "mode": row["mode"],
                "direction": row["direction"],
                "entry_time": row["entry_time"],
                "exit_time": row["exit_time"],
                "entry_price": row["entry_price"],
                "exit_price": row["exit_price"],
                "result": row["result"],
                "pnl_pct": row["pnl_pct"],
                "dollar_pnl": row["dollar_pnl"],
                "equity": row["equity"],
                "source": row["source"],
            }
        )
    return out


def build_snapshot(db_path: Path, trade_limit: int) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        symbols = _load_symbols(conn)
        results = {
            "backtest": _latest_results(conn, "backtest_results", "backtest"),
            "paper": _latest_results(conn, "paper_trading_results", "paper"),
            "live": _latest_results(conn, "live_trading_results", "live"),
        }
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "account": _latest_account(conn),
            "symbols": symbols,
            "results": results,
            "trades": _latest_trades(conn, trade_limit),
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export JSON snapshot for React dashboard")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to tradingcopilot.db")
    parser.add_argument("--trades", type=int, default=200, help="Recent trades to include")
    parser.add_argument(
        "--out",
        action="append",
        dest="outs",
        default=[],
        help="Output JSON path (repeatable). Defaults to docs/data and frontend-react/public/data",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: missing DB at {db_path}")
        return 2

    snapshot = build_snapshot(db_path=db_path, trade_limit=max(10, int(args.trades)))
    output_paths = [Path(p) for p in args.outs] if args.outs else DEFAULT_OUTPUTS

    for out_path in output_paths:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"Wrote {out_path}")

    print(
        "Export complete:",
        f"symbols={len(snapshot['symbols'])}",
        f"trades={len(snapshot['trades'])}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
