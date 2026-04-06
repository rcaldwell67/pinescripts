from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "strategy_generator"))

import backtest_backtrader_alpaca as backtest  # noqa: E402
import data.validate_dashboard_data_integrity as dashboard_integrity  # noqa: E402
import reset_aligned_backtest_paper as aligned_reset  # noqa: E402
from paper_trading.paper_trade_backtrader_alpaca import _metrics_for_trades  # noqa: E402

DEFAULT_SYMBOLS = ("BTC/USDT", "CLM")


@dataclass(frozen=True)
class ValidationTarget:
    symbol: str
    aligned_version: str = "v2"
    direct_version: str = "v6"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate representative rerun backtest paths against a temporary DB copy."
    )
    parser.add_argument(
        "--symbol",
        action="append",
        help="Symbol to validate. Repeat to run multiple symbols. Defaults to BTC/USDT and CLM.",
    )
    parser.add_argument(
        "--aligned-version",
        default="v2",
        choices=list(backtest.VERSION_MAP),
        help="Version to validate through the aligned reset path. Default: v2.",
    )
    parser.add_argument(
        "--direct-version",
        default="v6",
        choices=list(backtest.VERSION_MAP),
        help="Version to validate through the direct backtest path. Default: v6.",
    )
    return parser.parse_args()


def _normalized_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def _trade_count(conn: sqlite3.Connection, symbol: str, version: str, mode: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM trades
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND LOWER(version) = ?
          AND mode = ?
        """,
        (_normalized_symbol(symbol), version, mode),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _summary_count(conn: sqlite3.Connection, table: str, symbol: str, version: str) -> int:
    version_note = backtest.VERSION_MAP[version]
    row = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE UPPER(symbol) = ? AND notes LIKE ?",
        (symbol.upper(), f"%{version_note}%"),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _run_aligned_rerun(temp_db: Path, target: ValidationTarget) -> tuple[int, int]:
    print(f"[aligned] {target.symbol} {target.aligned_version}")
    df = backtest.fetch_ohlcv(target.symbol)
    trades = backtest.run_backtest(df, target.aligned_version, symbol=target.symbol)

    conn = sqlite3.connect(str(temp_db), timeout=60)
    try:
        version_note = backtest.VERSION_MAP[target.aligned_version]
        aligned_reset._clear_existing(conn, target.symbol, target.aligned_version, version_note)
        rows = aligned_reset._build_rows(target.symbol, target.aligned_version, trades, df)
        aligned_reset._insert_trades(conn, "backtest", rows)
        aligned_reset._insert_trades(conn, "paper", rows)

        metrics = _metrics_for_trades(target.symbol, target.aligned_version, trades, df)
        aligned_reset._insert_summary(conn, "backtest_results", target.symbol, metrics, f"{version_note} backtest summary")
        aligned_reset._insert_summary(
            conn,
            "paper_trading_results",
            target.symbol,
            metrics,
            f"{version_note} paper trading summary",
        )
        conn.commit()
    finally:
        conn.close()

    backtest_rows = len(rows)
    print(f"  bars={len(df):,} backtest_rows={backtest_rows} paper_rows={backtest_rows}")
    return len(df), backtest_rows


def _run_direct_rerun(temp_db: Path, target: ValidationTarget) -> tuple[int, int]:
    print(f"[direct] {target.symbol} {target.direct_version}")
    previous_db_path = backtest.DB_PATH
    backtest.DB_PATH = temp_db
    try:
        df = backtest.fetch_ohlcv(target.symbol)
        trades = backtest.run_backtest(df, target.direct_version, symbol=target.symbol)
        backtest.save_to_db(target.symbol, target.direct_version, trades, df)
    finally:
        backtest.DB_PATH = previous_db_path

    print(f"  bars={len(df):,} backtest_rows={len(trades)}")
    return len(df), len(trades)


def _assert_target_rows(conn: sqlite3.Connection, target: ValidationTarget) -> None:
    aligned_backtest = _trade_count(conn, target.symbol, target.aligned_version, "backtest")
    aligned_paper = _trade_count(conn, target.symbol, target.aligned_version, "paper")
    direct_backtest = _trade_count(conn, target.symbol, target.direct_version, "backtest")

    if aligned_backtest != aligned_paper:
        raise RuntimeError(
            f"aligned row mismatch for {target.symbol} {target.aligned_version}: backtest={aligned_backtest} paper={aligned_paper}"
        )

    if _summary_count(conn, "backtest_results", target.symbol, target.aligned_version) != 1:
        raise RuntimeError(f"expected one backtest summary for {target.symbol} {target.aligned_version}")
    if _summary_count(conn, "paper_trading_results", target.symbol, target.aligned_version) != 1:
        raise RuntimeError(f"expected one paper summary for {target.symbol} {target.aligned_version}")
    if _summary_count(conn, "backtest_results", target.symbol, target.direct_version) != 1:
        raise RuntimeError(f"expected one backtest summary for {target.symbol} {target.direct_version}")

    print(
        f"[ok] {target.symbol}: aligned_backtest={aligned_backtest} aligned_paper={aligned_paper} direct_backtest={direct_backtest}"
    )


def main() -> int:
    args = _parse_args()
    selected_symbols = [symbol.strip() for symbol in (args.symbol or list(DEFAULT_SYMBOLS)) if symbol and symbol.strip()]
    targets = [
        ValidationTarget(symbol=symbol, aligned_version=args.aligned_version, direct_version=args.direct_version)
        for symbol in selected_symbols
    ]

    base_db = Path(backtest.DB_PATH)
    if not base_db.exists():
        print(f"ERROR: missing DB at {base_db}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db = Path(temp_dir) / base_db.name
        shutil.copy2(base_db, temp_db)

        try:
            for target in targets:
                _run_aligned_rerun(temp_db, target)
                _run_direct_rerun(temp_db, target)

            conn = sqlite3.connect(str(temp_db), timeout=30)
            try:
                for target in targets:
                    _assert_target_rows(conn, target)
            finally:
                conn.close()

            previous_integrity_db = dashboard_integrity.DB_PATH
            dashboard_integrity.DB_PATH = temp_db
            try:
                status = dashboard_integrity.main()
            finally:
                dashboard_integrity.DB_PATH = previous_integrity_db

            if status != 0:
                raise RuntimeError(f"dashboard integrity validator failed with exit code {status}")
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print("Rerun backtest validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())