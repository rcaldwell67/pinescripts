from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

from backtest_backtrader_alpaca import run_backtest  # noqa: E402
from live_trading import realtime_alpaca_live_trader as live  # noqa: E402
from paper_trading import realtime_alpaca_paper_trader as paper  # noqa: E402
from v1_params import get_v1_params  # noqa: E402
from v2_params import get_v2_params  # noqa: E402
from v3_params import get_v3_params  # noqa: E402
from v4_params import get_v4_params  # noqa: E402
from v5_params import get_v5_params  # noqa: E402
from v6_params import get_v6_params  # noqa: E402

ACCOUNT_EQUITY = 100000.0
VERSIONS = ("v1", "v2", "v3", "v4", "v5", "v6")
PARAM_LOADERS = {
    "v1": get_v1_params,
    "v2": get_v2_params,
    "v3": get_v3_params,
    "v4": get_v4_params,
    "v5": get_v5_params,
    "v6": get_v6_params,
}
CONFIG_PATHS = {
    version: REPO_ROOT / "backend" / "strategy_generator" / "configs" / f"{version}_runtime.json"
    for version in VERSIONS
}


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _load_sample() -> pd.DataFrame:
    raise RuntimeError("Sample CSV loading is no longer supported. Please provide a valid DataFrame source.")


def _flatten_paths(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.extend(_flatten_paths(value, path))
        else:
            out.append((path, value))
    return out


def _get_path_value(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split("."):
        value = value[key]
    return value


def _top_level_overrides(version: str) -> dict[str, dict[str, Any]]:
    cfg_path = CONFIG_PATHS[version]
    if not cfg_path.exists():
        return {}
    loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
    overrides = loaded.get("symbol_overrides") if isinstance(loaded, dict) else {}
    return overrides if isinstance(overrides, dict) else {}


def _shared_enabled_side(baseline_params: dict[str, Any], override_params: dict[str, Any]) -> str | None:
    base_signal = baseline_params.get("signal", {}) if isinstance(baseline_params, dict) else {}
    over_signal = override_params.get("signal", {}) if isinstance(override_params, dict) else {}

    base_longs = bool(base_signal.get("enable_longs", False))
    base_shorts = bool(base_signal.get("enable_shorts", True))
    over_longs = bool(over_signal.get("enable_longs", False))
    over_shorts = bool(over_signal.get("enable_shorts", True))

    if base_longs and over_longs:
        return "long"
    if base_shorts and over_shorts:
        return "short"
    return None


def main() -> int:
    print("ERROR: This script requires a sample DataFrame, but sample CSV loading is no longer supported.", file=sys.stderr)
    return 1

    checked_versions = 0

    for version in VERSIONS:
        overrides = _top_level_overrides(version)
        if not overrides:
            print(f"SKIP {version}: no top-level symbol overrides configured")
            continue

        symbol, override_cfg = next(iter(overrides.items()))
        loader = PARAM_LOADERS[version]
        baseline = loader(symbol="UNMATCHED_SYMBOL")
        expected = loader(symbol=symbol)
        override_paths = _flatten_paths(override_cfg)
        differing_paths = [path for path, _ in override_paths if _get_path_value(expected, path) != _get_path_value(baseline, path)]
        if not differing_paths:
            return fail(f"{version} override for {symbol} does not change any effective parameter")

        paper_params = paper._strategy_params(version, symbol)
        live_params = live._strategy_params(version, symbol)
        for path in differing_paths:
            expected_value = _get_path_value(expected, path)
            if _get_path_value(paper_params, path) != expected_value:
                return fail(f"paper runner ignored {version} override {symbol} {path}")
            if _get_path_value(live_params, path) != expected_value:
                return fail(f"live runner ignored {version} override {symbol} {path}")

        try:
            trades = run_backtest(df.copy(), version, symbol=symbol)
        except Exception as exc:
            return fail(f"run_backtest failed for {version} symbol={symbol}: {exc}")
        if trades is None:
            return fail(f"run_backtest returned None for {version} symbol={symbol}")

        if any(path.startswith("risk.") for path in differing_paths):
            side = _shared_enabled_side(baseline, expected)
            if side is None:
                return fail(
                    f"no shared enabled side for risk validation in {version} symbol={symbol}"
                )

            baseline_df = df.copy()
            override_df = df.copy()
            live._entry_analysis(baseline_df, side=side, version=version, symbol="UNMATCHED_SYMBOL")
            live._entry_analysis(override_df, side=side, version=version, symbol=symbol)
            base_order = live._compute_order_params(
                baseline_df,
                ACCOUNT_EQUITY,
                side=side,
                version=version,
                symbol="UNMATCHED_SYMBOL",
            )
            override_order = live._compute_order_params(
                override_df,
                ACCOUNT_EQUITY,
                side=side,
                version=version,
                symbol=symbol,
            )
            if base_order is None or override_order is None:
                return fail(f"order param calculation failed for {version} symbol={symbol}")
            if base_order == override_order:
                return fail(f"risk override did not affect live order params for {version} symbol={symbol}")

        checked_versions += 1
        print(
            f"OK {version}: symbol={symbol} override_paths={len(differing_paths)} "
            f"trades={len(trades)}"
        )

    if checked_versions == 0:
        return fail("No symbol overrides found to validate")

    print("Symbol override dispatch validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())