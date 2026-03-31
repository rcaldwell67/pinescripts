from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

from apm_v1_backtest import backtest_apm_v1
from v1_params import get_v1_params


def load_ohlcv_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "timestamp" not in df.columns and "datetime" in df.columns:
        df = df.rename(columns={"datetime": "timestamp"})
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )


def score_trades(trades: pd.DataFrame, initial_equity: float) -> tuple[float, dict[str, float]]:
    if trades.empty:
        return -1e9, {"net_return_pct": 0.0, "max_dd_pct": 0.0, "trades": 0}

    pnl_col = "pnl" if "pnl" in trades.columns else "dollar_pnl"
    equity = trades["equity"].astype(float)
    peak = equity.cummax()
    max_dd_abs = float((peak - equity).max())
    max_dd_pct = (max_dd_abs / initial_equity * 100.0) if initial_equity else 0.0
    total_pnl = float(trades[pnl_col].sum())
    net_return_pct = (total_pnl / initial_equity * 100.0) if initial_equity else 0.0

    # Penalize drawdown and very low trade counts.
    trade_penalty = 0.0 if len(trades) >= 15 else (15 - len(trades)) * 0.25
    score = net_return_pct - (0.6 * max_dd_pct) - trade_penalty
    return score, {
        "net_return_pct": net_return_pct,
        "max_dd_pct": max_dd_pct,
        "trades": int(len(trades)),
    }


def apply_overrides(base: dict, overrides: dict[str, float]) -> dict:
    out = json.loads(json.dumps(base))
    out["signal"]["pullback_tolerance_pct"] = overrides["pullback_tolerance_pct"]
    out["risk"]["sl_atr_mult"] = overrides["sl_atr_mult"]
    out["risk"]["tp_atr_mult"] = overrides["tp_atr_mult"]
    out["risk"]["trail_activate_atr_mult"] = overrides["trail_activate_atr_mult"]
    out["risk"]["trail_dist_atr_mult"] = overrides["trail_dist_atr_mult"]
    return out


def run() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward optimizer for APM v1 parameters.")
    parser.add_argument(
        "--csv",
        default="backend/data/btc_usd_5m_ytd.csv",
        help="OHLCV csv path with timestamp/open/high/low/close/volume columns",
    )
    parser.add_argument("--folds", type=int, default=4, help="Number of walk-forward folds")
    parser.add_argument(
        "--out",
        default="backend/strategy_generator/configs/v1_optimized_walkforward.json",
        help="Output JSON for best params",
    )
    args = parser.parse_args()

    df = load_ohlcv_csv(Path(args.csv))
    params_base = get_v1_params()
    initial_equity = float(params_base["risk"]["initial_equity"])

    grid = {
        "pullback_tolerance_pct": [0.30, 0.40, 0.50],
        "sl_atr_mult": [3.5, 4.0, 4.5],
        "tp_atr_mult": [6.0, 8.0, 10.0],
        "trail_activate_atr_mult": [2.5, 3.5, 4.0],
        "trail_dist_atr_mult": [0.10, 0.15],
    }

    combos = list(
        itertools.product(
            grid["pullback_tolerance_pct"],
            grid["sl_atr_mult"],
            grid["tp_atr_mult"],
            grid["trail_activate_atr_mult"],
            grid["trail_dist_atr_mult"],
        )
    )

    n = len(df)
    fold_size = max(50, n // (args.folds + 1))

    fold_results: list[dict] = []
    selected_params: list[dict] = []

    for fold in range(args.folds):
        train_end = fold_size * (fold + 1)
        test_end = min(n, train_end + fold_size)
        if test_end - train_end < 20:
            break

        train_df = df.iloc[:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()

        best_score = -1e18
        best_overrides: dict[str, float] | None = None

        for combo in combos:
            overrides = {
                "pullback_tolerance_pct": combo[0],
                "sl_atr_mult": combo[1],
                "tp_atr_mult": combo[2],
                "trail_activate_atr_mult": combo[3],
                "trail_dist_atr_mult": combo[4],
            }
            params = apply_overrides(params_base, overrides)
            train_trades = backtest_apm_v1(train_df.copy(), params=params)
            score, _ = score_trades(train_trades, initial_equity)
            if score > best_score:
                best_score = score
                best_overrides = overrides

        if best_overrides is None:
            continue

        chosen = apply_overrides(params_base, best_overrides)
        test_trades = backtest_apm_v1(test_df.copy(), params=chosen)
        _, test_metrics = score_trades(test_trades, initial_equity)

        fold_results.append(
            {
                "fold": fold + 1,
                "train_rows": len(train_df),
                "test_rows": len(test_df),
                "selected_overrides": best_overrides,
                "test_metrics": test_metrics,
            }
        )
        selected_params.append(best_overrides)

    if not selected_params:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "fold_results": fold_results,
                    "recommended_params": params_base,
                    "note": "No folds produced valid optimization results; returning current runtime parameters.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("No folds produced valid optimization results. Wrote fallback runtime parameters.")
        return 0

    def avg(key: str) -> float:
        return sum(float(p[key]) for p in selected_params) / len(selected_params)

    final = apply_overrides(
        params_base,
        {
            "pullback_tolerance_pct": round(avg("pullback_tolerance_pct"), 4),
            "sl_atr_mult": round(avg("sl_atr_mult"), 4),
            "tp_atr_mult": round(avg("tp_atr_mult"), 4),
            "trail_activate_atr_mult": round(avg("trail_activate_atr_mult"), 4),
            "trail_dist_atr_mult": round(avg("trail_dist_atr_mult"), 4),
        },
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"fold_results": fold_results, "recommended_params": final}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote walk-forward recommendation to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
