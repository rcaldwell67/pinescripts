from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

from apm_v2_backtest import backtest_apm_v2  # noqa: E402
from backtest_backtrader_alpaca import fetch_ohlcv  # noqa: E402
from v3_params import get_v3_params  # noqa: E402
from v4_params import get_v4_params  # noqa: E402
from v5_params import get_v5_params  # noqa: E402
from v6_params import get_v6_params  # noqa: E402

SUPPORTED_VERSIONS = {"v3", "v4", "v5", "v6"}
PARAM_LOADERS = {
    "v3": get_v3_params,
    "v4": get_v4_params,
    "v5": get_v5_params,
    "v6": get_v6_params,
}


@dataclass
class EvalResult:
    trades: int
    win_rate: float
    net_return_pct: float
    max_drawdown_pct: float


def normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def evaluate(df, version: str, params: dict[str, Any], symbol: str) -> EvalResult:
    trades = backtest_apm_v2(df.copy(), params=params)
    if trades.empty:
        return EvalResult(0, 0.0, 0.0, 0.0)

    start_equity = float(trades["equity"].iloc[0] - trades["pnl"].iloc[0])
    win_rate = float((trades["pnl"] > 0).mean() * 100.0)
    net_return = float((trades["equity"].iloc[-1] / start_equity - 1.0) * 100.0) if start_equity else 0.0
    equity = trades["equity"].astype(float)
    max_dd = float(((equity.cummax() - equity) / equity.cummax() * 100.0).max())
    return EvalResult(int(len(trades)), win_rate, net_return, max_dd)


def _deep_copy(data: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(data))


def _set_nested(data: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    cursor = data
    for key in keys[:-1]:
        child = cursor.get(key)
        if not isinstance(child, dict):
            child = {}
            cursor[key] = child
        cursor = child
    cursor[keys[-1]] = value


def candidate_grid(version: str, symbol: str) -> dict[str, list[Any]]:
    is_crypto = "/" in symbol
    grid: dict[str, list[Any]] = {
        "signal.enable_longs": [True, False] if is_crypto else [True, False],
        "signal.enable_shorts": [True, False] if is_crypto else [True, False],
        "signal.pullback_tolerance_pct": [0.15, 0.2, 0.25, 0.3, 0.35],
        "signal.momentum_bars": [3, 4, 5, 6, 8],
        "signal.rsi_long_min": [38, 40, 42, 44, 46],
        "signal.rsi_long_max": [58, 60, 62, 64, 66],
        "signal.rsi_short_min": [28, 30, 32, 34],
        "signal.rsi_short_max": [50, 54, 58, 62],
        "signal.adx_slope_bars": [0, 1, 2],
        "signal.adx_threshold": [12, 14, 16, 18, 20, 22],
        "signal.di_spread": [0.0, 2.5, 5.0, 7.5],
        "signal.session_filter_enabled": [False, True],
        "signal.session_start_hour_et": [8, 9, 10],
        "signal.session_end_hour_et": [13, 14, 15, 16],
        "signal.volume_mult_min": [0.3, 0.5, 0.7, 0.9],
        "signal.min_body_atr_mult": [0.10, 0.15, 0.20],
        "signal.atr_floor_pct": [0.08, 0.10, 0.12, 0.15],
        "signal.panic_suppression_mult": [1.2, 1.5, 1.8, 2.0],
        "risk.sl_atr_mult": [1.5, 2.0, 2.5, 3.0, 3.5],
        "risk.tp_atr_mult": [4.0, 5.0, 6.0, 8.0, 10.0],
        "risk.trail_activate_atr_mult": [1.5, 2.0, 2.5, 3.0],
        "risk.trail_dist_atr_mult": [0.05, 0.08, 0.10, 0.12, 0.15],
        "risk.risk_pct": [0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0],
        "risk.max_bars_in_trade": [20, 30, 40, 60],
    }
    if version == "v3":
        grid.update(
            {
                "signal.rvol_filter_enabled": [True, False],
                "signal.rvol_min": [1.0, 1.05, 1.1, 1.2],
                "signal.atr_percentile_filter_enabled": [True, False],
                "signal.atr_percentile_min": [15.0, 20.0, 25.0, 30.0, 35.0],
                "signal.atr_percentile_max": [85.0, 90.0, 95.0],
            }
        )
    if version in {"v4", "v5", "v6"}:
        grid.update(
            {
                "signal.bb_filter_enabled": [True, False],
                "signal.bb_width_pct_min": [0.6, 0.8, 1.0, 1.25, 1.5],
                "signal.donchian_filter_enabled": [True, False],
                "signal.donchian_len": [10, 15, 20, 30],
            }
        )
    return grid


def apply_candidate(base_params: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    out = _deep_copy(base_params)
    for path, value in candidate.items():
        _set_nested(out, path, value)
    return out


def rank_key(
    result: EvalResult,
    min_win_rate: float,
    min_net_return: float,
    max_drawdown: float,
) -> tuple[int, int, int, float, float, int]:
    pass_wr = int(result.win_rate >= min_win_rate)
    pass_net = int(result.net_return_pct >= min_net_return)
    pass_dd = int(result.max_drawdown_pct <= max_drawdown)
    pass_all = int(pass_wr and pass_net and pass_dd)
    pass_count = pass_wr + pass_net + pass_dd

    dd_penalty = max(0.0, result.max_drawdown_pct - max_drawdown)
    wr_deficit = max(0.0, min_win_rate - result.win_rate)
    net_deficit = max(0.0, min_net_return - result.net_return_pct)
    total_deficit = (4.0 * wr_deficit / max(min_win_rate, 1e-9)) + (1.5 * net_deficit / max(min_net_return, 1e-9)) + (
        dd_penalty / max(max_drawdown, 1e-9)
    )
    return (pass_all, pass_wr, pass_count, -total_deficit, result.net_return_pct, result.trades)


def update_runtime_config(config_path: Path, symbol: str, candidate: dict[str, Any]) -> None:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    symbol_overrides = data.setdefault("symbol_overrides", {})
    sym_key = normalize_symbol(symbol)
    override = symbol_overrides.setdefault(sym_key, {})
    for path, value in candidate.items():
        _set_nested(override, path, value)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run() -> int:
    parser = argparse.ArgumentParser(description="Tune v3-v6 per-symbol settings and optionally apply top-level runtime overrides.")
    parser.add_argument("--version", required=True, help="Strategy version (v3-v6)")
    parser.add_argument("--symbol", required=True, help="Symbol to tune, e.g. BTC/USD")
    parser.add_argument("--max-evals", type=int, default=80, help="Number of random candidates to evaluate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--min-win-rate", type=float, default=70.0, help="Target: minimum win-rate percentage")
    parser.add_argument("--min-net-return", type=float, default=20.0, help="Target: minimum net return percentage")
    parser.add_argument("--max-drawdown", type=float, default=4.5, help="Target: maximum drawdown percentage")
    parser.add_argument("--out", default="docs/data/v3_v6_profile_tuning_result.json", help="Path to write tuning result JSON")
    parser.add_argument("--apply", action="store_true", help="Apply best candidate to the version runtime config")
    args = parser.parse_args()

    version = args.version.strip().lower()
    if version not in SUPPORTED_VERSIONS:
        raise SystemExit(f"Unsupported version {version!r}; expected one of {sorted(SUPPORTED_VERSIONS)}")

    random.seed(args.seed)
    grid = candidate_grid(version, args.symbol)
    keys = list(grid.keys())
    loader = PARAM_LOADERS[version]

    df = fetch_ohlcv(args.symbol)
    base = loader(symbol=args.symbol)
    base_result = evaluate(df, version, base, args.symbol)

    best_candidate: dict[str, Any] | None = None
    best_result: EvalResult | None = None

    for _ in range(max(args.max_evals, 1)):
        candidate = {key: random.choice(grid[key]) for key in keys}
        if not candidate["signal.enable_longs"] and not candidate["signal.enable_shorts"]:
            continue
        if not candidate["signal.session_filter_enabled"]:
            candidate["signal.session_start_hour_et"] = base["signal"].get("session_start_hour_et", 9)
            candidate["signal.session_end_hour_et"] = base["signal"].get("session_end_hour_et", 14)
        params = apply_candidate(base, candidate)
        result = evaluate(df, version, params, args.symbol)
        if best_result is None or rank_key(result, args.min_win_rate, args.min_net_return, args.max_drawdown) > rank_key(
            best_result,
            args.min_win_rate,
            args.min_net_return,
            args.max_drawdown,
        ):
            best_result = result
            best_candidate = candidate

    assert best_result is not None and best_candidate is not None

    payload = {
        "version": version,
        "symbol": args.symbol,
        "targets": {
            "win_rate_min": args.min_win_rate,
            "net_return_min": args.min_net_return,
            "max_drawdown_max": args.max_drawdown,
        },
        "base": {
            "trades": base_result.trades,
            "win_rate": base_result.win_rate,
            "net_return_pct": base_result.net_return_pct,
            "max_drawdown_pct": base_result.max_drawdown_pct,
            "pass_all": rank_key(base_result, args.min_win_rate, args.min_net_return, args.max_drawdown)[0] == 1,
        },
        "best_candidate": {
            **best_candidate,
            "trades": best_result.trades,
            "win_rate": best_result.win_rate,
            "net_return_pct": best_result.net_return_pct,
            "max_drawdown_pct": best_result.max_drawdown_pct,
            "pass_win_rate": best_result.win_rate >= args.min_win_rate,
            "pass_net_return": best_result.net_return_pct >= args.min_net_return,
            "pass_drawdown": best_result.max_drawdown_pct <= args.max_drawdown,
            "pass_all": rank_key(best_result, args.min_win_rate, args.min_net_return, args.max_drawdown)[0] == 1,
        },
        "evaluations": args.max_evals,
        "seed": args.seed,
    }

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote tuning result to {out_path}")
    print(json.dumps(payload["best_candidate"], indent=2))

    if not payload["best_candidate"]["pass_all"]:
        print(f"WARNING: Best candidate does not pass all guidelines. Runtime config will NOT be updated.")
        print(f"  Win Rate: {best_result.win_rate:.2f}% (required: >={args.min_win_rate}%, passed: {payload['best_candidate']['pass_win_rate']})")
        print(f"  Net Return: {best_result.net_return_pct:.2f}% (required: >={args.min_net_return}%, passed: {payload['best_candidate']['pass_net_return']})")
        print(f"  Max Drawdown: {best_result.max_drawdown_pct:.2f}% (required: <={args.max_drawdown}%, passed: {payload['best_candidate']['pass_drawdown']})")
        return 0

    if args.apply:
        config_path = REPO_ROOT / "backend" / "strategy_generator" / "configs" / f"{version}_runtime.json"
        update_runtime_config(config_path, args.symbol, best_candidate)
        print(f"Applied best candidate to {config_path} symbol={args.symbol}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())