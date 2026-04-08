"""
Update guideline_matrix_all_versions.json from latest tuning result files.

Reads existing matrix, then overwrites entries that have a newer tuning result
in docs/data/v*_profile_tuning_result_*_guideline_retry.json.

Run after all targeted tuning jobs complete:
  python update_guideline_matrix.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MATRIX_PATH = REPO_ROOT / "docs" / "data" / "guideline_matrix_all_versions.json"
DATA_DIR = REPO_ROOT / "docs" / "data"

sys.path.insert(0, str(REPO_ROOT / "backend"))

from config.guideline_policy import evaluate_backtest_guideline  # noqa: E402

THRESHOLDS = {"min_win_rate": 65.0, "min_net_return": 15.0, "max_drawdown": 4.5, "min_trades": 10}
SYMBOL_MAP = {
    "ethbtc": "ETH/BTC",
    "ethusdc": "ETH/USDC",
    "ethusdt": "ETH/USDT",
    "btcusdt": "BTC/USDT",
    "btcusdc": "BTC/USDC",
    "btcusd": "BTC/USD",
    "ethusd": "ETH/USD",
    "clm": "CLM",
    "crf": "CRF",
}

_RETRY_PATTERN = re.compile(r"^(v[1-6])_profile_tuning_result_([a-z]+)_guideline_retry\.json$")


def load_retry_results() -> dict[tuple[str, str], dict]:
    """Return {(version, symbol): {'candidate': ..., 'timestamp': ...}} from retry result files."""
    results: dict[tuple[str, str], dict] = {}
    for f in DATA_DIR.glob("*_guideline_retry.json"):
        m = _RETRY_PATTERN.match(f.name)
        if not m:
            continue
        version, sym_key = m.group(1), m.group(2)
        symbol = SYMBOL_MAP.get(sym_key)
        if not symbol:
            print(f"  WARNING: Unknown symbol key '{sym_key}' in {f.name}", file=sys.stderr)
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ERROR reading {f.name}: {e}", file=sys.stderr)
            continue
        bc = data.get("best_candidate") or data
        results[(version, symbol)] = {
            "candidate": bc,
            "timestamp": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
    return results


def main() -> int:
    if not MATRIX_PATH.exists():
        print(f"ERROR: Matrix file not found: {MATRIX_PATH}", file=sys.stderr)
        return 1

    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    records: list[dict] = matrix.get("records", [])

    retry_results = load_retry_results()
    print(f"Loaded {len(retry_results)} retry result(s): {sorted(retry_results.keys())}")

    updated = 0
    for rec in records:
        key = (rec["version"], rec["symbol"])
        if key not in retry_results:
            continue
        retry_result = retry_results[key]
        bc = retry_result["candidate"]
        wr = float(bc.get("win_rate", bc.get("win_rate_pct", 0.0)))
        net = float(bc.get("net_return_pct", 0.0))
        dd = float(bc.get("max_drawdown_pct", 0.0))
        trades = int(bc.get("trades", 0))
        symbol = rec["symbol"]
        passed, r = evaluate_backtest_guideline(symbol, rec["version"], trades, wr, net, dd)
        rec.update(
            {
                "timestamp": retry_result["timestamp"],
                "trades": trades,
                "win_rate_pct": wr,
                "net_return_pct": net,
                "max_drawdown_pct": dd,
                "pass_all": passed,
                "reasons": r,
            }
        )
        print(f"  Updated {key}: WR={wr:.1f}% net={net:.1f}% DD={dd:.2f}% pass={passed}")
        updated += 1

    re_evaluated = 0
    for rec in records:
        trades = int(rec.get("trades", 0))
        wr = float(rec.get("win_rate_pct", 0.0))
        net = float(rec.get("net_return_pct", 0.0))
        dd = float(rec.get("max_drawdown_pct", 0.0))
        passed, reasons = evaluate_backtest_guideline(rec["symbol"], rec["version"], trades, wr, net, dd)
        rec["pass_all"] = passed
        rec["reasons"] = reasons
        re_evaluated += 1

    MATRIX_PATH.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    print(f"\nMatrix updated ({updated} retry entries). Re-evaluated {re_evaluated} total records. Written to {MATRIX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
