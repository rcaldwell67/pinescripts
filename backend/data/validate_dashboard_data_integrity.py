"""Validate dashboard data integrity across symbols and v1-v7.

Checks:
- Missing (symbol, version) combos in trades for backtest and paper modes.
- Summary-vs-trade drift for net return % in backtest_results and paper_trading_results.

Usage:
    python backend/data/validate_dashboard_data_integrity.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "docs" / "data" / "tradingcopilot.db"
VERSIONS = ("v1", "v2", "v3", "v4", "v5", "v6", "v7")
SYM_NORM_SQL = "REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '')"


@dataclass
class TradeMetrics:
    beginning_equity: float
    final_equity: float

    @property
    def net_return_pct(self) -> float:
        if self.beginning_equity <= 0:
            return 0.0
        return (self.final_equity - self.beginning_equity) / self.beginning_equity * 100.0


def _version_from_notes_or_metrics(notes: str, metrics_json: str) -> str:
    m = re.search(r"\b(v[1-6])\b", str(notes or ""), flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    try:
        payload = json.loads(metrics_json or "{}")
    except Exception:
        return ""
    return str(payload.get("version") or "").strip().lower()


def _load_symbols(conn: sqlite3.Connection) -> list[str]:
    return [str(r[0]) for r in conn.execute("SELECT symbol FROM symbols ORDER BY symbol").fetchall()]


def _missing_trade_combos(conn: sqlite3.Connection, mode: str, symbols: list[str]) -> list[tuple[str, str]]:
    rows = conn.execute(
        f"""
        SELECT DISTINCT {SYM_NORM_SQL} AS sym_key, LOWER(version) AS version
        FROM trades
        WHERE mode = ?
        """,
        (mode,),
    ).fetchall()
    existing = {(str(sym), str(ver)) for sym, ver in rows}

    missing: list[tuple[str, str]] = []
    for symbol in symbols:
        sym_key = "".join(ch for ch in symbol.upper() if ch.isalnum())
        for version in VERSIONS:
            if (sym_key, version) not in existing:
                missing.append((symbol, version))
    return missing


def _trade_metrics(conn: sqlite3.Connection, mode: str) -> dict[tuple[str, str], TradeMetrics]:
    rows = conn.execute(
        f"""
        WITH ordered AS (
            SELECT
                {SYM_NORM_SQL} AS sym_key,
                LOWER(version) AS version,
                equity,
                COALESCE(dollar_pnl, 0) AS dollar_pnl,
                ROW_NUMBER() OVER (
                    PARTITION BY {SYM_NORM_SQL}, LOWER(version)
                    ORDER BY datetime(COALESCE(exit_time, entry_time)) ASC, id ASC
                ) AS rn_first,
                ROW_NUMBER() OVER (
                    PARTITION BY {SYM_NORM_SQL}, LOWER(version)
                    ORDER BY datetime(COALESCE(exit_time, entry_time)) DESC, id DESC
                ) AS rn_last
            FROM trades
            WHERE mode = ? AND equity IS NOT NULL
        )
        SELECT
            f.sym_key,
            f.version,
                        (f.equity - f.dollar_pnl) AS beginning_equity,
            l.equity AS final_equity
        FROM ordered f
        JOIN ordered l
          ON l.sym_key = f.sym_key AND l.version = f.version
        WHERE f.rn_first = 1 AND l.rn_last = 1
        """,
        (mode,),
    ).fetchall()

    out: dict[tuple[str, str], TradeMetrics] = {}
    for sym_key, version, beginning_eq, final_eq in rows:
        out[(str(sym_key), str(version))] = TradeMetrics(float(beginning_eq), float(final_eq))
    return out


def _summary_net_returns(conn: sqlite3.Connection, table: str) -> dict[tuple[str, str], float]:
    rows = conn.execute(
        f"SELECT symbol, notes, metrics FROM {table}"
    ).fetchall()
    out: dict[tuple[str, str], float] = {}
    for symbol, notes, metrics_json in rows:
        version = _version_from_notes_or_metrics(str(notes or ""), str(metrics_json or ""))
        if version not in VERSIONS:
            continue
        try:
            payload = json.loads(metrics_json or "{}")
        except Exception:
            continue
        net_ret = payload.get("net_return_pct")
        if isinstance(net_ret, (int, float)):
            sym_key = "".join(ch for ch in str(symbol).upper() if ch.isalnum())
            out[(sym_key, version)] = float(net_ret)
    return out


def _summary_versions(conn: sqlite3.Connection, table: str) -> set[tuple[str, str]]:
    rows = conn.execute(f"SELECT symbol, notes, metrics FROM {table}").fetchall()
    versions: set[tuple[str, str]] = set()
    for symbol, notes, metrics_json in rows:
        version = _version_from_notes_or_metrics(str(notes or ""), str(metrics_json or ""))
        if version not in VERSIONS:
            continue
        sym_key = "".join(ch for ch in str(symbol).upper() if ch.isalnum())
        versions.add((sym_key, version))
    return versions


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: missing DB at {DB_PATH}")
        return 2

    conn = sqlite3.connect(DB_PATH)
    try:
        symbols = _load_symbols(conn)

        print("== Missing Coverage ==")
        for mode in ("backtest", "paper"):
            missing = _missing_trade_combos(conn, mode, symbols)
            print(f"{mode}: missing trades for {len(missing)} symbol/version combos")
            for symbol, version in missing:
                print(f"  - {symbol} {version}")

            summary_table = "backtest_results" if mode == "backtest" else "paper_trading_results"
            summary_versions = _summary_versions(conn, summary_table)
            effective_missing: list[tuple[str, str]] = []
            for symbol in symbols:
                sym_key = "".join(ch for ch in symbol.upper() if ch.isalnum())
                for version in VERSIONS:
                    if (symbol, version) in missing and (sym_key, version) not in summary_versions:
                        effective_missing.append((symbol, version))
            print(f"{mode}: effective missing (no trades and no summary) = {len(effective_missing)}")
            for symbol, version in effective_missing:
                print(f"  - {symbol} {version}")

        print("\n== Summary vs Trades Drift (net_return_pct) ==")
        checks = [
            ("backtest", "backtest_results"),
            ("paper", "paper_trading_results"),
        ]
        for mode, table in checks:
            trade_map = _trade_metrics(conn, mode)
            summary_map = _summary_net_returns(conn, table)
            print(f"{table} against {mode} trades")
            drift_count = 0
            for key, summary_ret in sorted(summary_map.items()):
                trade = trade_map.get(key)
                if not trade:
                    continue
                trade_ret = trade.net_return_pct
                delta = summary_ret - trade_ret
                if abs(delta) > 0.5:
                    drift_count += 1
                    print(
                        f"  - {key[0]} {key[1]} summary={summary_ret:.4f}% trades={trade_ret:.4f}% delta={delta:+.4f}%"
                    )
            if drift_count == 0:
                print("  - no material drift detected")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
