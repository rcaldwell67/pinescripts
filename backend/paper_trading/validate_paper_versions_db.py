from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from backtest_backtrader_alpaca import VERSION_MAP, run_backtest  # noqa: E402
from paper_trading import paper_trade_backtrader_alpaca as paper_runner  # noqa: E402

BASE_DB = REPO_ROOT / "frontend-react" / "public" / "data" / "tradingcopilot.db"
VERSIONS = ("v1", "v2", "v3", "v4", "v5", "v6")
SYMBOL = "BTC/USD"


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_sample_df() -> pd.DataFrame:
    raise RuntimeError("Sample CSV loading is no longer supported. Please provide a valid DataFrame source.")


def _normalized_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def main() -> int:
    if not BASE_DB.exists():
        return fail(f"Missing base DB: {BASE_DB}")

    print("ERROR: This script requires a sample DataFrame, but sample CSV loading is no longer supported.", file=sys.stderr)
    return 1

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db = Path(temp_dir) / "tradingcopilot_temp.db"
        shutil.copy2(BASE_DB, temp_db)
        paper_runner.DB_PATH = temp_db

        expected_counts: dict[str, int] = {}
        expected_dirs: dict[str, set[str]] = {}

        for version in VERSIONS:
            try:
                trades = run_backtest(df.copy(), version, symbol=SYMBOL)
                paper_runner.save_paper_to_db(SYMBOL, version, trades, df, force_reset=True)
            except Exception as exc:
                return fail(f"paper DB validation failed for {version}: {exc}")

            expected_counts[version] = len(trades)
            if "side" in trades.columns and len(trades):
                expected_dirs[version] = {str(v).strip().lower() for v in trades["side"].dropna().tolist()}
            else:
                expected_dirs[version] = {"short"} if len(trades) else set()

        conn = sqlite3.connect(str(temp_db))
        try:
            norm_symbol = _normalized_symbol(SYMBOL)
            for version in VERSIONS:
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_trading_results
                    WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
                      AND notes LIKE ?
                    """,
                    (norm_symbol, f"%{VERSION_MAP.get(version, version)}%"),
                ).fetchone()
                summary_count = int(row[0] or 0) if row else 0
                if summary_count != 1:
                    return fail(f"expected one paper summary row for {version}, found {summary_count}")

                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM trades
                    WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
                      AND LOWER(version) = ?
                      AND mode = 'paper'
                    """,
                    (norm_symbol, version),
                ).fetchone()
                actual_count = int(row[0] or 0) if row else 0
                if actual_count != expected_counts[version]:
                    return fail(
                        f"paper trade count mismatch for {version}: expected {expected_counts[version]}, got {actual_count}"
                    )

                if expected_counts[version] > 0:
                    rows = conn.execute(
                        """
                        SELECT DISTINCT LOWER(direction)
                        FROM trades
                        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
                          AND LOWER(version) = ?
                          AND mode = 'paper'
                        """,
                        (norm_symbol, version),
                    ).fetchall()
                    actual_dirs = {str(row[0]).strip().lower() for row in rows if row[0] is not None}
                    if actual_dirs != expected_dirs[version]:
                        return fail(
                            f"paper direction mismatch for {version}: expected {sorted(expected_dirs[version])}, got {sorted(actual_dirs)}"
                        )

                print(
                    f"OK {version}: summary=1 trades={actual_count} directions={sorted(expected_dirs[version])}"
                )
        finally:
            conn.close()

    print("Paper DB version validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
