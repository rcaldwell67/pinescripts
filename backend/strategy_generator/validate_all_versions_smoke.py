from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

from backtest_backtrader_alpaca import run_backtest  # noqa: E402
from live_trading import realtime_alpaca_live_trader as live  # noqa: E402
from paper_trading import realtime_alpaca_paper_trader as paper  # noqa: E402

VERSIONS = ("v1", "v2", "v3", "v4", "v5", "v6")
SAMPLE_CSV = REPO_ROOT / "backend" / "data" / "btc_usd_5m_ytd.csv"


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _load_sample() -> pd.DataFrame:
    if not SAMPLE_CSV.exists():
        raise FileNotFoundError(f"Missing sample CSV: {SAMPLE_CSV}")

    df = pd.read_csv(SAMPLE_CSV)
    if len(df) < 400:
        raise RuntimeError(f"Sample CSV has insufficient rows: {len(df)}")

    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    required = {"timestamp", "Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Sample CSV missing required columns: {missing}")
    return df


def main() -> int:
    try:
        df = _load_sample()
    except Exception as exc:
        return fail(str(exc))

    backtest_df = df.head(1500).copy()
    realtime_df = df.head(400).copy()

    for version in VERSIONS:
        try:
            trades = run_backtest(backtest_df.copy(), version, symbol="BTC/USD")
        except Exception as exc:
            return fail(f"run_backtest failed for {version}: {exc}")

        if trades is None:
            return fail(f"run_backtest returned None for {version}")

        try:
            paper_entry = paper._entry_analysis(realtime_df.copy(), "short", version)
            paper_exit = paper._exit_analysis(realtime_df.copy(), "short", version)
            live_entry = live._entry_analysis(realtime_df.copy(), "short", version)
        except Exception as exc:
            return fail(f"realtime analysis dispatch failed for {version}: {exc}")

        if not isinstance(paper_entry, dict):
            return fail(f"paper entry analysis did not return dict for {version}")
        if not isinstance(paper_exit, dict):
            return fail(f"paper exit analysis did not return dict for {version}")
        if not isinstance(live_entry, dict):
            return fail(f"live entry analysis did not return dict for {version}")

        trade_count = len(trades)
        print(
            f"OK {version}: trades={trade_count} "
            f"paper_failed_stage={paper_entry.get('failed_stage')} "
            f"live_failed_stage={live_entry.get('failed_stage')}"
        )

    print("All version smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())