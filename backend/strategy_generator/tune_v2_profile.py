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
from apm_v2_backtest import backtest_apm_v2  # noqa: E402
from v2_params import get_v2_params  # noqa: E402

WIN_RATE_TARGET = 70.0
NET_RETURN_TARGET = 20.0
MAX_DD_TARGET = 4.5


@dataclass
class EvalResult:
    trades: int
    win_rate: float
    net_return_pct: float
    max_drawdown_pct: float


def normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def evaluate(df, params: dict[str, Any]) -> EvalResult:
    trades = backtest_apm_v2(df.copy(), params=params)
    if trades.empty:
        return EvalResult(0, 0.0, 0.0, 0.0)

    start_equity = float(trades["equity"].iloc[0] - trades["pnl"].iloc[0])
    win_rate = float((trades["pnl"] > 0).mean() * 100.0)
    net_return = float((trades["equity"].iloc[-1] / start_equity - 1.0) * 100.0) if start_equity else 0.0
    equity = trades["equity"].astype(float)
    max_dd = float(((equity.cummax() - equity) / equity.cummax() * 100.0).max())
    return EvalResult(int(len(trades)), win_rate, net_return, max_dd)


def candidate_grid(symbol: str) -> dict[str, list[Any]]:
    is_crypto = "/" in symbol
    return {
        "enable_longs": [True, False] if is_crypto else [False],
        "enable_shorts": [True, False] if is_crypto else [True],
        "pullback_tolerance_pct": [0.15, 0.2, 0.25, 0.3, 0.35],
        "momentum_bars": [3, 4, 5, 6, 8],
        "rsi_long_min": [38, 40, 42, 44, 46],
        "rsi_long_max": [58, 60, 62, 64, 66],
        "rsi_short_min": [28, 30, 32, 34],
        "rsi_short_max": [50, 54, 58, 62],
        "adx_slope_bars": [0, 1, 2],
        "adx_threshold": [12, 14, 16, 18, 20, 22],
        "di_spread": [0.0, 2.5, 5.0, 7.5],
        "session_filter_enabled": [False, True],
        "session_start_hour_et": [8, 9, 10],
        "session_end_hour_et": [13, 14, 15, 16],
        "volume_mult_min": [0.3, 0.5, 0.7, 0.9],
        "min_body_atr_mult": [0.10, 0.15, 0.20],
        "atr_floor_pct": [0.08, 0.10, 0.12, 0.15],
        "panic_suppression_mult": [1.2, 1.5, 1.8, 2.0],
        "sl_atr_mult": [1.5, 2.0, 2.5, 3.0, 3.5],
        "tp_atr_mult": [4.0, 5.0, 6.0, 8.0, 10.0],
        "trail_activate_atr_mult": [1.5, 2.0, 2.5, 3.0],
        "trail_dist_atr_mult": [0.05, 0.08, 0.1, 0.12, 0.15],
        "risk_pct": [0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0],
        "max_bars_in_trade": [20, 30, 40, 60],
    }


def apply_candidate(base_params: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base_params))
    out["signal"]["enable_longs"] = c["enable_longs"]
    out["signal"]["enable_shorts"] = c["enable_shorts"]
    out["signal"]["pullback_tolerance_pct"] = c["pullback_tolerance_pct"]
    out["signal"]["momentum_bars"] = c["momentum_bars"]
    out["signal"]["rsi_long_min"] = c["rsi_long_min"]
    out["signal"]["rsi_long_max"] = c["rsi_long_max"]
    out["signal"]["rsi_short_min"] = c["rsi_short_min"]
    out["signal"]["rsi_short_max"] = c["rsi_short_max"]
    out["signal"]["adx_slope_bars"] = c["adx_slope_bars"]
    out["signal"]["adx_threshold"] = c["adx_threshold"]
    out["signal"]["di_spread"] = c["di_spread"]
    out["signal"]["session_filter_enabled"] = c["session_filter_enabled"]
    out["signal"]["session_start_hour_et"] = c["session_start_hour_et"]
    out["signal"]["session_end_hour_et"] = c["session_end_hour_et"]
    out["signal"]["volume_mult_min"] = c["volume_mult_min"]
    out["signal"]["min_body_atr_mult"] = c["min_body_atr_mult"]
    out["signal"]["atr_floor_pct"] = c["atr_floor_pct"]
    out["signal"]["panic_suppression_mult"] = c["panic_suppression_mult"]
    out["risk"]["sl_atr_mult"] = c["sl_atr_mult"]
    out["risk"]["tp_atr_mult"] = c["tp_atr_mult"]
    out["risk"]["trail_activate_atr_mult"] = c["trail_activate_atr_mult"]
    out["risk"]["trail_dist_atr_mult"] = c["trail_dist_atr_mult"]
    out["risk"]["risk_pct"] = c["risk_pct"]
    out["risk"]["max_bars_in_trade"] = c["max_bars_in_trade"]
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

    # Weight win-rate deficit highest to drive closure of the remaining failure mode.
    total_deficit = (4.0 * wr_deficit / max(min_win_rate, 1e-9)) + (1.5 * net_deficit / max(min_net_return, 1e-9)) + (
        dd_penalty / max(max_drawdown, 1e-9)
    )
    return (pass_all, pass_wr, pass_count, -total_deficit, result.net_return_pct, result.trades)


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
            "enable_longs": candidate["enable_longs"],
            "enable_shorts": candidate["enable_shorts"],
            "pullback_tolerance_pct": candidate["pullback_tolerance_pct"],
            "momentum_bars": candidate["momentum_bars"],
            "rsi_long_min": candidate["rsi_long_min"],
            "rsi_long_max": candidate["rsi_long_max"],
            "rsi_short_min": candidate["rsi_short_min"],
            "rsi_short_max": candidate["rsi_short_max"],
            "adx_slope_bars": candidate["adx_slope_bars"],
            "adx_threshold": candidate["adx_threshold"],
            "di_spread": candidate["di_spread"],
            "session_filter_enabled": candidate["session_filter_enabled"],
            "session_start_hour_et": candidate["session_start_hour_et"],
            "session_end_hour_et": candidate["session_end_hour_et"],
            "volume_mult_min": candidate["volume_mult_min"],
            "min_body_atr_mult": candidate["min_body_atr_mult"],
            "atr_floor_pct": candidate["atr_floor_pct"],
            "panic_suppression_mult": candidate["panic_suppression_mult"],
        },
        "risk": {
            "sl_atr_mult": candidate["sl_atr_mult"],
            "tp_atr_mult": candidate["tp_atr_mult"],
            "trail_activate_atr_mult": candidate["trail_activate_atr_mult"],
            "trail_dist_atr_mult": candidate["trail_dist_atr_mult"],
            "risk_pct": candidate["risk_pct"],
            "max_bars_in_trade": candidate["max_bars_in_trade"],
        },
    }
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run() -> int:
    parser = argparse.ArgumentParser(description="Tune v2 per-symbol settings under guideline constraints.")
    parser.add_argument("--symbol", required=True, help="Symbol to tune, e.g. BTC/USD")
    parser.add_argument("--max-evals", type=int, default=120, help="Number of random candidates to evaluate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--min-win-rate", type=float, default=WIN_RATE_TARGET, help="Target: minimum win-rate percentage")
    parser.add_argument("--min-net-return", type=float, default=NET_RETURN_TARGET, help="Target: minimum net return percentage")
    parser.add_argument("--max-drawdown", type=float, default=MAX_DD_TARGET, help="Target: maximum drawdown percentage")
    parser.add_argument("--profile", help="Optional v2 profile name; when set with --apply, writes profile-scoped overrides")
    parser.add_argument(
        "--out",
        default="docs/data/v2_profile_tuning_result.json",
        help="Path to write tuning result JSON",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply best candidate to backend/strategy_generator/configs/v2_runtime.json",
    )
    parser.add_argument(
        "--apply-best-available",
        action="store_true",
        help="When used with --apply, update runtime config with best candidate even if guideline targets are not fully met.",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    grid = candidate_grid(args.symbol)
    keys = list(grid.keys())

    df = fetch_ohlcv(args.symbol)
    base = get_v2_params(symbol=args.symbol, profile=args.profile)
    base_result = evaluate(df, base)

    best_candidate: dict[str, Any] | None = None
    best_result: EvalResult | None = None

    for _ in range(max(args.max_evals, 1)):
        c = {k: random.choice(grid[k]) for k in keys}
        # Enforce at least one side active.
        if not c["enable_longs"] and not c["enable_shorts"]:
            continue
        # If session filtering is disabled, session window does not matter and we keep runtime defaults.
        if not c["session_filter_enabled"]:
            c["session_start_hour_et"] = base["signal"].get("session_start_hour_et", 9)
            c["session_end_hour_et"] = base["signal"].get("session_end_hour_et", 14)
        params = apply_candidate(base, c)
        result = evaluate(df, params)
        if best_result is None or rank_key(result, args.min_win_rate, args.min_net_return, args.max_drawdown) > rank_key(
            best_result,
            args.min_win_rate,
            args.min_net_return,
            args.max_drawdown,
        ):
            best_result = result
            best_candidate = c

    assert best_result is not None and best_candidate is not None

    payload = {
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
        "profile": args.profile,
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
        if not (args.apply and args.apply_best_available):
            return 0
        print("Applying best available candidate despite target miss (--apply-best-available enabled).")

    if args.apply:
        config_path = REPO_ROOT / "backend" / "strategy_generator" / "configs" / "v2_runtime.json"
        update_runtime_config(config_path, args.symbol, best_candidate, profile=args.profile)
        if args.profile:
            print(f"Applied best candidate to {config_path} profile={args.profile} symbol={args.symbol}")
        else:
            print(f"Applied best candidate to {config_path} symbol={args.symbol}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
