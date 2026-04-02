"""
Validate missed realtime paper trading opportunities without placing orders.

This script reconstructs missed scheduler windows from `realtime_paper_log`,
replays entry analysis at each missed window, and reports whether any
executable paper-trading opportunities were missed for the selected date.

Usage:
    python backend/paper_trading/validate_missed_opportunities.py
    python backend/paper_trading/validate_missed_opportunities.py --date 2026-04-02
    python backend/paper_trading/validate_missed_opportunities.py --version v1
    python backend/paper_trading/validate_missed_opportunities.py --symbol BTC/USD --symbol ETH/USD
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
STRATEGY_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(STRATEGY_DIR))

from backtest_backtrader_alpaca import fetch_ohlcv  # noqa: E402
from paper_trading import realtime_alpaca_paper_trader as paper_runner  # noqa: E402

DEFAULT_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"


@dataclass
class Finding:
    window: str
    symbol: str
    version: str
    status: str
    side: str
    detail: str


@dataclass
class VersionAudit:
    version: str
    non_scheduler_rows: int
    schedule_miss_rows: int
    missed_windows: int
    executable_findings: list[Finding]
    blocked_findings: list[Finding]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate missed realtime paper trading opportunities for a date."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to tradingcopilot.db")
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).date().isoformat(),
        help="UTC date to audit in YYYY-MM-DD format (default: today UTC)",
    )
    parser.add_argument(
        "--version",
        action="append",
        help="Optional strategy version filter; can be passed multiple times",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        help="Optional symbol filter; can be passed multiple times",
    )
    parser.add_argument(
        "--schedule-interval-seconds",
        type=int,
        default=300,
        help="Expected scheduler cadence in seconds (default: 300)",
    )
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="Return nonzero if only blocked opportunities are found",
    )
    return parser.parse_args()


def _validate_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise SystemExit(f"Invalid --date value {text!r}: {exc}") from exc


def _versions_for_date(conn: sqlite3.Connection, audit_date: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT LOWER(version)
        FROM realtime_paper_log
        WHERE substr(logged_at, 1, 10) = ?
          AND version NOT IN ('', 'system')
        ORDER BY LOWER(version)
        """,
        (audit_date,),
    ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def _symbols_for_audit(symbol_args: list[str] | None) -> list[str]:
    if symbol_args:
        return [symbol.strip() for symbol in symbol_args if symbol and symbol.strip()]
    return paper_runner._load_symbols_from_db()


def _missed_windows_for_version(
    conn: sqlite3.Connection,
    audit_date: str,
    version: str,
    interval_seconds: int,
) -> tuple[int, int, list[datetime]]:
    threshold_seconds = interval_seconds * 1.5
    non_scheduler_rows = conn.execute(
        """
        SELECT logged_at
        FROM realtime_paper_log
        WHERE substr(logged_at, 1, 10) = ?
          AND LOWER(version) = ?
          AND symbol != '__scheduler__'
        ORDER BY logged_at ASC
        """,
        (audit_date, version),
    ).fetchall()
    schedule_miss_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM realtime_paper_log
        WHERE substr(logged_at, 1, 10) = ?
          AND status = 'schedule_miss'
        """,
        (audit_date,),
    ).fetchone()[0]

    times = [paper_runner._parse_iso_ts(row[0]) for row in non_scheduler_rows]
    times = [ts for ts in times if ts is not None]
    windows: list[datetime] = []
    for prev, curr in zip(times, times[1:]):
        gap_seconds = (curr - prev).total_seconds()
        if gap_seconds <= threshold_seconds:
            continue
        built = paper_runner._build_missed_windows(prev, curr, interval_seconds)
        for window_dt in built[:-1]:
            if window_dt.date().isoformat() == audit_date:
                windows.append(window_dt)

    deduped: list[datetime] = []
    seen = set()
    for window_dt in windows:
        key = window_dt.isoformat()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(window_dt)
    return len(times), int(schedule_miss_count or 0), deduped


def _slice_for_window(df, window_dt: datetime):
    if "timestamp" in df.columns:
        source_times = [str(v) for v in df["timestamp"].tolist()]
    elif "Datetime" in df.columns:
        source_times = [str(v) for v in df["Datetime"].tolist()]
    else:
        source_times = [str(v) for v in df.index.tolist()]

    candidate_idx = -1
    for idx, ts_raw in enumerate(source_times):
        ts = paper_runner._parse_iso_ts(ts_raw)
        if ts is not None and ts <= window_dt:
            candidate_idx = idx
    if candidate_idx < 210:
        return None
    return df.iloc[: candidate_idx + 1].copy()


def _audit_version(
    conn: sqlite3.Connection,
    audit_date: str,
    version: str,
    symbols: list[str],
    interval_seconds: int,
) -> VersionAudit:
    non_scheduler_rows, schedule_miss_rows, missed_windows = _missed_windows_for_version(
        conn,
        audit_date,
        version,
        interval_seconds,
    )

    data_cache = {symbol: fetch_ohlcv(symbol) for symbol in symbols}
    executable_findings: list[Finding] = []
    blocked_findings: list[Finding] = []

    for window_dt in missed_windows:
        for symbol, df in data_cache.items():
            if len(df) < 210:
                continue
            df_slice = _slice_for_window(df, window_dt)
            if df_slice is None:
                continue

            long_analysis = paper_runner._entry_analysis(df_slice, side="long", version=version)
            short_analysis = paper_runner._entry_analysis(df_slice, side="short", version=version)
            long_ok = bool(long_analysis.get("is_entry"))
            short_ok = bool(short_analysis.get("is_entry"))
            if not long_ok and not short_ok:
                continue

            if long_ok:
                executable_findings.append(
                    Finding(
                        window=window_dt.isoformat(),
                        symbol=symbol,
                        version=version,
                        status="missed_opportunity",
                        side="long",
                        detail=str(long_analysis.get("detail") or "long entry"),
                    )
                )
                continue

            if short_ok and paper_runner._can_short_symbol(symbol):
                executable_findings.append(
                    Finding(
                        window=window_dt.isoformat(),
                        symbol=symbol,
                        version=version,
                        status="missed_opportunity",
                        side="short",
                        detail=str(short_analysis.get("detail") or "short entry"),
                    )
                )
                continue

            blocked_findings.append(
                Finding(
                    window=window_dt.isoformat(),
                    symbol=symbol,
                    version=version,
                    status="missed_opportunity_blocked",
                    side="short",
                    detail=str(short_analysis.get("detail") or "short entry"),
                )
            )

    return VersionAudit(
        version=version,
        non_scheduler_rows=non_scheduler_rows,
        schedule_miss_rows=schedule_miss_rows,
        missed_windows=len(missed_windows),
        executable_findings=executable_findings,
        blocked_findings=blocked_findings,
    )


def _print_report(audit_date: str, symbols: list[str], audits: list[VersionAudit]) -> None:
    print(f"Audit date (UTC): {audit_date}")
    print(f"Symbols: {', '.join(symbols) if symbols else '(none)'}")
    for audit in audits:
        print(f"\n[{audit.version}]")
        print(f"  non_scheduler_rows: {audit.non_scheduler_rows}")
        print(f"  schedule_miss_rows: {audit.schedule_miss_rows}")
        print(f"  missed_windows: {audit.missed_windows}")
        print(f"  executable_misses: {len(audit.executable_findings)}")
        print(f"  blocked_misses: {len(audit.blocked_findings)}")

        if audit.executable_findings:
            print("  executable findings:")
            for finding in audit.executable_findings:
                print(
                    f"    - {finding.window} | {finding.symbol} | {finding.side} | {finding.detail}"
                )

        if audit.blocked_findings:
            print("  blocked findings:")
            for finding in audit.blocked_findings:
                print(
                    f"    - {finding.window} | {finding.symbol} | {finding.side} | {finding.detail}"
                )


def main() -> int:
    args = _parse_args()
    audit_date = _validate_date(args.date)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    try:
        versions = [v.strip().lower() for v in (args.version or []) if v and v.strip()]
        if not versions:
            versions = _versions_for_date(conn, audit_date)
        if not versions:
            print(f"No realtime paper log versions found for {audit_date}.")
            return 0

        symbols = _symbols_for_audit(args.symbol)
        if not symbols:
            print("No symbols available for audit.")
            return 0

        audits = [
            _audit_version(
                conn,
                audit_date,
                version,
                symbols,
                args.schedule_interval_seconds,
            )
            for version in versions
        ]
        _print_report(audit_date, symbols, audits)

        executable_total = sum(len(audit.executable_findings) for audit in audits)
        blocked_total = sum(len(audit.blocked_findings) for audit in audits)
        if executable_total > 0:
            print(f"\nFAILED: found {executable_total} executable missed opportunity(s).", file=sys.stderr)
            return 1
        if blocked_total > 0 and args.fail_on_blocked:
            print(f"\nFAILED: found {blocked_total} blocked missed opportunity(s).", file=sys.stderr)
            return 1

        print("\nPASSED: no executable missed opportunities found.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())