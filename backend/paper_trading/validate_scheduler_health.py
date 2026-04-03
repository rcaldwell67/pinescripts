"""
Validate realtime paper trading scheduler health from realtime_paper_log.

This script audits scheduler cadence for a UTC date and fails when runtime gaps
or logged schedule_miss events exceed the configured tolerance.

Usage:
    python backend/paper_trading/validate_scheduler_health.py
    python backend/paper_trading/validate_scheduler_health.py --date 2026-04-02
    python backend/paper_trading/validate_scheduler_health.py --version v1
    python backend/paper_trading/validate_scheduler_health.py --max-schedule-misses 2
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
STRATEGY_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(STRATEGY_DIR))

from paper_trading import realtime_alpaca_paper_trader as paper_runner  # noqa: E402

DEFAULT_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"


@dataclass
class VersionHealth:
    version: str
    non_scheduler_rows: int
    schedule_miss_rows: int
    max_gap_minutes: float
    latest_gap_minutes: float | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate realtime paper trading scheduler health for a UTC date."
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
        "--schedule-interval-seconds",
        type=int,
        default=300,
        help="Expected scheduler cadence in seconds (default: 300)",
    )
    parser.add_argument(
        "--max-schedule-misses",
        type=int,
        default=0,
        help="Maximum allowed schedule_miss rows before failing (default: 0)",
    )
    parser.add_argument(
        "--max-gap-minutes",
        type=float,
        help="Optional hard cap for observed gap minutes; default derives from cadence threshold",
    )
    parser.add_argument(
        "--recent-window-minutes",
        type=float,
        help=(
            "Optional sliding lookback window (minutes) for today's audit. "
            "When set, counts and gap checks only include rows at/after now-window."
        ),
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


def _window_start_for_today(audit_date: str, recent_window_minutes: float | None) -> datetime | None:
    if recent_window_minutes is None or recent_window_minutes <= 0:
        return None
    today_utc = datetime.now(timezone.utc).date().isoformat()
    if audit_date != today_utc:
        return None
    return datetime.now(timezone.utc) - timedelta(minutes=recent_window_minutes)


def _load_non_scheduler_times(
    conn: sqlite3.Connection,
    audit_date: str,
    version: str,
    window_start: datetime | None = None,
) -> list[datetime]:
    rows = conn.execute(
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
    times = [paper_runner._parse_iso_ts(row[0]) for row in rows]
    filtered = [ts for ts in times if ts is not None]
    if window_start is not None:
        filtered = [ts for ts in filtered if ts >= window_start]
    return filtered


def _schedule_miss_count(
    conn: sqlite3.Connection,
    audit_date: str,
    window_start: datetime | None = None,
) -> int:
    rows = conn.execute(
        """
        SELECT logged_at
        FROM realtime_paper_log
        WHERE substr(logged_at, 1, 10) = ?
          AND status = 'schedule_miss'
        """,
        (audit_date,),
    ).fetchall()
    if not rows:
        return 0

    if window_start is None:
        return len(rows)

    count = 0
    for row in rows:
        ts = paper_runner._parse_iso_ts(row[0])
        if ts is not None and ts >= window_start:
            count += 1
    return count


def _max_gap_minutes(times: list[datetime]) -> float:
    if len(times) < 2:
        return 0.0
    max_gap_seconds = max((curr - prev).total_seconds() for prev, curr in zip(times, times[1:]))
    return max_gap_seconds / 60.0


def _latest_gap_minutes(times: list[datetime], audit_date: str) -> float | None:
    if not times:
        return None
    today_utc = datetime.now(timezone.utc).date().isoformat()
    if audit_date != today_utc:
        return None
    return (datetime.now(timezone.utc) - times[-1]).total_seconds() / 60.0


def _audit_version(
    conn: sqlite3.Connection,
    audit_date: str,
    version: str,
    window_start: datetime | None = None,
) -> VersionHealth:
    times = _load_non_scheduler_times(conn, audit_date, version, window_start)
    return VersionHealth(
        version=version,
        non_scheduler_rows=len(times),
        schedule_miss_rows=_schedule_miss_count(conn, audit_date, window_start),
        max_gap_minutes=_max_gap_minutes(times),
        latest_gap_minutes=_latest_gap_minutes(times, audit_date),
    )


def _print_report(
    audit_date: str,
    audits: list[VersionHealth],
    threshold_minutes: float,
    recent_window_minutes: float | None = None,
    window_start: datetime | None = None,
) -> None:
    print(f"Audit date (UTC): {audit_date}")
    print(f"Cadence threshold: {threshold_minutes:.1f}m")
    if recent_window_minutes is not None and recent_window_minutes > 0:
        print(f"Recent window: last {recent_window_minutes:.1f}m (today UTC only)")
        if window_start is not None:
            print(f"Window start (UTC): {window_start.isoformat()}")
    for audit in audits:
        print(f"\n[{audit.version}]")
        print(f"  non_scheduler_rows: {audit.non_scheduler_rows}")
        print(f"  schedule_miss_rows: {audit.schedule_miss_rows}")
        print(f"  max_gap_minutes: {audit.max_gap_minutes:.1f}")
        if audit.latest_gap_minutes is not None:
            print(f"  latest_gap_minutes: {audit.latest_gap_minutes:.1f}")


def main() -> int:
    args = _parse_args()
    audit_date = _validate_date(args.date)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 2

    if args.schedule_interval_seconds <= 0:
        print("ERROR: --schedule-interval-seconds must be > 0", file=sys.stderr)
        return 2

    threshold_minutes = (args.schedule_interval_seconds * 1.5) / 60.0
    gap_limit_minutes = args.max_gap_minutes if args.max_gap_minutes is not None else threshold_minutes

    conn = sqlite3.connect(str(db_path))
    try:
        versions = [v.strip().lower() for v in (args.version or []) if v and v.strip()]
        if not versions:
            versions = _versions_for_date(conn, audit_date)
        if not versions:
            print(f"No realtime paper log versions found for {audit_date}.")
            return 0

        window_start = _window_start_for_today(audit_date, args.recent_window_minutes)
        audits = [_audit_version(conn, audit_date, version, window_start) for version in versions]
        _print_report(
            audit_date,
            audits,
            threshold_minutes,
            args.recent_window_minutes,
            window_start,
        )

        failures: list[str] = []
        schedule_miss_rows = _schedule_miss_count(conn, audit_date, window_start)
        if schedule_miss_rows > args.max_schedule_misses:
            failures.append(
                f"schedule_miss rows {schedule_miss_rows} exceed allowed {args.max_schedule_misses}"
            )

        for audit in audits:
            if audit.max_gap_minutes > gap_limit_minutes:
                failures.append(
                    f"{audit.version} max gap {audit.max_gap_minutes:.1f}m exceeds allowed {gap_limit_minutes:.1f}m"
                )
            if audit.latest_gap_minutes is not None and audit.latest_gap_minutes > gap_limit_minutes:
                failures.append(
                    f"{audit.version} latest gap {audit.latest_gap_minutes:.1f}m exceeds allowed {gap_limit_minutes:.1f}m"
                )

        if failures:
            print("\nFAILED:", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1

        print("\nPASSED: scheduler cadence is within configured tolerance.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())