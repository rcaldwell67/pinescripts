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

from backtest_backtrader_alpaca import fetch_ohlcv  # noqa: E402
from apm_v1_backtest import backtest_apm_v1  # noqa: E402
from v1_params import get_v1_params  # noqa: E402


@dataclass
class EvalResult:
    trades: int
    win_rate: float
    net_return_pct: float
    max_drawdown_pct: float


def normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def evaluate(df, params: dict[str, Any]) -> EvalResult:
    trades = backtest_apm_v1(df.copy(), params=params)
    if trades.empty:
        return EvalResult(0, 0.0, 0.0, 0.0)

    start_equity = float(trades["equity"].iloc[0] - trades["pnl"].iloc[0])
    win_rate = float((trades["pnl"] > 0).mean() * 100.0)
    net_return = float((trades["equity"].iloc[-1] / start_equity - 1.0) * 100.0) if start_equity else 0.0
    equity = trades["equity"].astype(float)
    max_dd = float(((equity.cummax() - equity) / equity.cummax() * 100.0).max())
    return EvalResult(int(len(trades)), win_rate, net_return, max_dd)


def candidate_grid() -> dict[str, list[Any]]:
    return {
        "pullback_tolerance_pct": [0.2, 0.25, 0.3, 0.35],
        "rsi_short_max": [48, 50, 52, 54, 56],
        "adx_threshold": [15, 16, 18, 20, 22],
        "di_spread": [0.0, 2.5, 5.0, 7.5],
        "session_filter_enabled": [False, True],
        "sl_atr_mult": [3.5, 4.0, 4.5],
        "tp_atr_mult": [6.0, 8.0, 10.0],
        "trail_activate_atr_mult": [2.0, 2.5, 3.0],
        "trail_dist_atr_mult": [0.06, 0.08, 0.10],
        "risk_pct": [0.6, 0.7, 0.8, 0.9, 1.0, 1.2],
    }


def apply_candidate(base_params: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base_params))
    out["signal"]["pullback_tolerance_pct"] = c["pullback_tolerance_pct"]
    out["signal"]["rsi_short_max"] = c["rsi_short_max"]
    out["signal"]["adx_threshold"] = c["adx_threshold"]
    out["signal"]["di_spread"] = c["di_spread"]
    out["signal"]["session_filter_enabled"] = c["session_filter_enabled"]
    out["risk"]["sl_atr_mult"] = c["sl_atr_mult"]
    out["risk"]["tp_atr_mult"] = c["tp_atr_mult"]
    out["risk"]["trail_activate_atr_mult"] = c["trail_activate_atr_mult"]
    out["risk"]["trail_dist_atr_mult"] = c["trail_dist_atr_mult"]
    out["risk"]["risk_pct"] = c["risk_pct"]
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

    return (
        pass_all,
        pass_wr,
        pass_count,
        -total_deficit,
        result.net_return_pct,
        result.trades,
    )


def update_runtime_profile(
    config_path: Path,
    profile_name: str,
    symbol: str,
    candidate: dict[str, Any],
) -> None:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    profiles = data.setdefault("profiles", {})
    profile = profiles.setdefault(profile_name, {})
    symbol_overrides = profile.setdefault("symbol_overrides", {})
    sym_key = normalize_symbol(symbol)
    symbol_overrides[sym_key] = {
        "signal": {
            "pullback_tolerance_pct": candidate["pullback_tolerance_pct"],
            "rsi_short_max": candidate["rsi_short_max"],
            "adx_threshold": candidate["adx_threshold"],
            "di_spread": candidate["di_spread"],
            "session_filter_enabled": candidate["session_filter_enabled"],
        },
        "risk": {
            "sl_atr_mult": candidate["sl_atr_mult"],
            "tp_atr_mult": candidate["tp_atr_mult"],
            "trail_activate_atr_mult": candidate["trail_activate_atr_mult"],
            "trail_dist_atr_mult": candidate["trail_dist_atr_mult"],
            "risk_pct": candidate["risk_pct"],
        },
    }
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def update_runtime_config(
    config_path: Path,
    symbol: str,
    candidate: dict[str, Any],
    profile: str | None = None,
) -> None:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    container = data
    if profile:
        profiles = data.setdefault("profiles", {})
        container = profiles.setdefault(profile, {})

    symbol_overrides = container.setdefault("symbol_overrides", {})
    sym_key = normalize_symbol(symbol)
    symbol_overrides[sym_key] = {
        "signal": {
            "pullback_tolerance_pct": candidate["pullback_tolerance_pct"],
            "rsi_short_max": candidate["rsi_short_max"],
            "adx_threshold": candidate["adx_threshold"],
            "di_spread": candidate["di_spread"],
            "session_filter_enabled": candidate["session_filter_enabled"],
        },
        "risk": {
            "sl_atr_mult": candidate["sl_atr_mult"],
            "tp_atr_mult": candidate["tp_atr_mult"],
            "trail_activate_atr_mult": candidate["trail_activate_atr_mult"],
            "trail_dist_atr_mult": candidate["trail_dist_atr_mult"],
            "risk_pct": candidate["risk_pct"],
        },
    }
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run() -> int:
    parser = argparse.ArgumentParser(description="Tune v1 per-symbol profile settings under guideline constraints.")
    parser.add_argument("--symbol", default="ETH/USD", help="Symbol to tune, e.g. ETH/USD")
    parser.add_argument("--profile", default="eth_focus", help="Profile name to tune")
    parser.add_argument("--max-evals", type=int, default=60, help="Number of random candidates to evaluate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--min-win-rate", type=float, default=70.0, help="Constraint: minimum win-rate pct")
    parser.add_argument("--min-net-return", type=float, default=20.0, help="Constraint: minimum net return pct")
    parser.add_argument("--max-drawdown", type=float, default=4.5, help="Constraint: maximum drawdown pct")
    parser.add_argument(
        "--out",
        default="docs/data/v1_profile_tuning_result.json",
        help="Path to write tuning result JSON",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply best candidate to backend/strategy_generator/configs/v1_runtime.json",
    )
    parser.add_argument(
        "--apply-top-level",
        action="store_true",
        help="Apply best candidate to the top-level symbol_overrides instead of a named profile",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    grid = candidate_grid()
    keys = list(grid.keys())

    df = fetch_ohlcv(args.symbol)
    base = get_v1_params(symbol=args.symbol, profile=args.profile)
    base_result = evaluate(df, base)

    best_candidate: dict[str, Any] | None = None
    best_result: EvalResult | None = None

    for _ in range(max(args.max_evals, 1)):
        c = {k: random.choice(grid[k]) for k in keys}
        params = apply_candidate(base, c)
        result = evaluate(df, params)
        if best_result is None or rank_key(result, args.min_win_rate, args.min_net_return, args.max_drawdown) > rank_key(
            best_result, args.min_win_rate, args.min_net_return, args.max_drawdown
        ):
            best_result = result
            best_candidate = c

    assert best_result is not None and best_candidate is not None

    payload = {
        "symbol": args.symbol,
        "profile": args.profile,
        "constraints": {
            "min_win_rate": args.min_win_rate,
            "min_net_return": args.min_net_return,
            "max_drawdown": args.max_drawdown,
        },
        "base": {
            "trades": base_result.trades,
            "win_rate": base_result.win_rate,
            "net_return_pct": base_result.net_return_pct,
            "max_drawdown_pct": base_result.max_drawdown_pct,
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
            "meets_constraints": best_result.net_return_pct >= args.min_net_return
            and best_result.max_drawdown_pct <= args.max_drawdown,
            "pass_all": best_result.win_rate >= args.min_win_rate
            and best_result.net_return_pct >= args.min_net_return
            and best_result.max_drawdown_pct <= args.max_drawdown,
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
        print(f"WARNING: Best candidate does not meet all constraints. Runtime config will NOT be updated.")
        print(f"  Win Rate: {best_result.win_rate:.2f}% (required: >={args.min_win_rate}%)")
        print(f"  Net Return: {best_result.net_return_pct:.2f}% (required: >={args.min_net_return}%)")
        print(f"  Max Drawdown: {best_result.max_drawdown_pct:.2f}% (required: <={args.max_drawdown}%)")
        return 0

    if args.apply:
        config_path = REPO_ROOT / "backend" / "strategy_generator" / "configs" / "v1_runtime.json"
        if args.apply_top_level:
            update_runtime_config(config_path, args.symbol, best_candidate)
            print(f"Applied best candidate to {config_path} symbol={args.symbol}")
        else:
            update_runtime_profile(config_path, args.profile, args.symbol, best_candidate)
            print(f"Applied best candidate to {config_path} profile={args.profile} symbol={args.symbol}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
