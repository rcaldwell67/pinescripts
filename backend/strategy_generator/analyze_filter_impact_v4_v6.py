"""Analyze v4/v6 entry opportunities filtered by Bollinger/Donchian gates.

This script compares entry eligibility with current params vs a counterfactual
where the new gates are disabled:
- bb_filter_enabled
- donchian_filter_enabled

It reports how many opportunities were filtered specifically by:
- bb_width
- donchian_break

Usage:
    python backend/strategy_generator/analyze_filter_impact_v4_v6.py
    python backend/strategy_generator/analyze_filter_impact_v4_v6.py --version v4
    python backend/strategy_generator/analyze_filter_impact_v4_v6.py --symbol BTC/USD
"""

from __future__ import annotations

import argparse
import copy
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

from apm_v1 import _evaluate_long_entry_at, _evaluate_short_entry_at, _prepare_signal_frame  # noqa: E402
from backtest_backtrader_alpaca import DB_PATH, fetch_ohlcv  # noqa: E402
from v4_params import get_v4_params  # noqa: E402
from v6_params import get_v6_params  # noqa: E402

TARGET_FAILED_STAGES = {"bb_width", "donchian_break"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze v4/v6 filter impact by failed stage.")
    parser.add_argument("--version", action="append", choices=["v4", "v6"], help="Version to analyze (repeatable).")
    parser.add_argument("--symbol", action="append", help="Optional symbol filter (repeatable).")
    parser.add_argument("--max-examples", type=int, default=8, help="Max examples per failed stage (default: 8).")
    return parser.parse_args()


def _load_symbols(symbol_args: list[str] | None) -> list[str]:
    if symbol_args:
        return [s.strip() for s in symbol_args if s and s.strip()]
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute("SELECT symbol FROM symbols ORDER BY symbol").fetchall()
        return [str(r[0]) for r in rows]
    finally:
        conn.close()


def _params_for_version(version: str, symbol: str) -> dict:
    if version == "v4":
        return get_v4_params(symbol=symbol)
    if version == "v6":
        return get_v6_params(symbol=symbol)
    raise ValueError(f"Unsupported version: {version}")


def _calc_start_idx(signal: dict) -> int:
    slope_lookback = int(signal.get("ema_slope_lookback", 3))
    momentum_bars = int(signal.get("momentum_bars", 5))
    adx_slope_bars = int(signal.get("adx_slope_bars", 0))
    atr_pct_window = int(signal.get("atr_percentile_window", 120)) if bool(signal.get("atr_percentile_filter_enabled", False)) else 0
    bb_len = int(signal.get("bb_len", 20)) if bool(signal.get("bb_filter_enabled", False)) else 0
    donchian_len = int(signal.get("donchian_len", 20)) if bool(signal.get("donchian_filter_enabled", False)) else 0
    ema_slow = int(signal.get("ema_slow", 200))
    return max(ema_slow, slope_lookback + 1, momentum_bars, adx_slope_bars, atr_pct_window, bb_len, donchian_len + 1)


def _format_ts(df, i: int) -> str:
    if "timestamp" in df.columns:
        return str(df.iloc[i].get("timestamp"))
    return str(df.index[i])


def _eval_side(df, i: int, signal: dict, et_hours, side: str) -> dict:
    if side == "long":
        return _evaluate_long_entry_at(df, i, signal, et_hours)
    return _evaluate_short_entry_at(df, i, signal, et_hours)


def _analyze_symbol(version: str, symbol: str, max_examples: int) -> dict:
    params_full = _params_for_version(version, symbol)
    params_counterfactual = copy.deepcopy(params_full)
    params_counterfactual.setdefault("signal", {})
    params_counterfactual["signal"]["bb_filter_enabled"] = False
    params_counterfactual["signal"]["donchian_filter_enabled"] = False

    df_raw = fetch_ohlcv(symbol)
    df_full = df_raw.copy()
    df_no = df_raw.copy()

    signal_full, _ts_full, et_hours_full = _prepare_signal_frame(df_full, params_full)
    signal_no, _ts_no, et_hours_no = _prepare_signal_frame(df_no, params_counterfactual)

    start = max(_calc_start_idx(signal_full), _calc_start_idx(signal_no))

    sides: list[str] = []
    if bool(signal_full.get("enable_longs", True)):
        sides.append("long")
    if bool(signal_full.get("enable_shorts", True)):
        sides.append("short")

    out = {
        "bars": len(df_raw),
        "entries_full": 0,
        "entries_without_new_filters": 0,
        "filtered_by_stage": defaultdict(int),
        "examples": defaultdict(list),
    }

    for i in range(start, len(df_raw)):
        for side in sides:
            r_full = _eval_side(df_full, i, signal_full, et_hours_full, side)
            r_no = _eval_side(df_no, i, signal_no, et_hours_no, side)

            if bool(r_full.get("is_entry")):
                out["entries_full"] += 1
            if bool(r_no.get("is_entry")):
                out["entries_without_new_filters"] += 1

            if bool(r_no.get("is_entry")) and not bool(r_full.get("is_entry")):
                failed_stage = str(r_full.get("failed_stage") or "unknown")
                if failed_stage in TARGET_FAILED_STAGES:
                    out["filtered_by_stage"][failed_stage] += 1
                    examples = out["examples"][failed_stage]
                    if len(examples) < max_examples:
                        examples.append(
                            {
                                "ts": _format_ts(df_raw, i),
                                "side": side,
                                "detail": str(r_full.get("detail") or ""),
                            }
                        )

    return out


def main() -> int:
    args = _parse_args()
    versions = args.version or ["v4", "v6"]
    symbols = _load_symbols(args.symbol)

    if not symbols:
        print("No symbols found.")
        return 0

    for version in versions:
        print(f"\n=== Filter Impact: {version.upper()} ===")
        total_full = 0
        total_no = 0
        total_stage = defaultdict(int)

        for symbol in symbols:
            try:
                summary = _analyze_symbol(version, symbol, args.max_examples)
            except Exception as exc:
                print(f"{symbol}: ERROR {exc}")
                continue

            total_full += int(summary["entries_full"])
            total_no += int(summary["entries_without_new_filters"])
            for stage, count in summary["filtered_by_stage"].items():
                total_stage[stage] += int(count)

            print(
                f"{symbol}: entries_with_filters={summary['entries_full']} "
                f"entries_without_new_filters={summary['entries_without_new_filters']} "
                f"blocked_bb_width={summary['filtered_by_stage'].get('bb_width', 0)} "
                f"blocked_donchian_break={summary['filtered_by_stage'].get('donchian_break', 0)}"
            )

            for stage in sorted(TARGET_FAILED_STAGES):
                examples = summary["examples"].get(stage, [])
                if not examples:
                    continue
                print(f"  examples[{stage}]:")
                for ex in examples:
                    print(f"    - {ex['ts']} | {ex['side']} | {ex['detail']}")

        print(
            f"TOTAL {version.upper()}: entries_with_filters={total_full} "
            f"entries_without_new_filters={total_no} "
            f"blocked_bb_width={total_stage.get('bb_width', 0)} "
            f"blocked_donchian_break={total_stage.get('donchian_break', 0)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
