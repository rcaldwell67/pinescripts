from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "backend" / "strategy_generator" / "configs" / "v1_runtime.json"

REQUIRED_KEYS = {
    "signal": {
        "ema_fast",
        "ema_mid",
        "ema_slow",
        "ema_slope_lookback",
        "rsi_len",
        "rsi_short_min",
        "rsi_short_max",
        "pullback_tolerance_pct",
        "volume_sma_len",
        "volume_mult_min",
        "min_body_atr_mult",
        "atr_len",
        "atr_floor_pct",
    },
    "risk": {
        "sl_atr_mult",
        "tp_atr_mult",
        "trail_activate_atr_mult",
        "trail_dist_atr_mult",
        "risk_pct",
        "max_bars_in_trade",
        "initial_equity",
    },
}

TARGET_FILES = [
    REPO_ROOT / "backend" / "strategy_generator" / "apm_v1.py",
    REPO_ROOT / "backend" / "strategy_generator" / "apm_v1_backtest.py",
    REPO_ROOT / "backend" / "paper_trading" / "realtime_alpaca_paper_trader.py",
    REPO_ROOT / "backend" / "live_trading" / "realtime_alpaca_live_trader.py",
]

FORBIDDEN_SNIPPETS = [
    "4.0 * atr",
    "8.0 * atr",
    "0.02",
    "ATR_MULT_SL",
    "ATR_MULT_TP",
    "ATR_MULT_TRAIL_ACT",
    "ATR_MULT_TRAIL_DIST",
]


def fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    if not CONFIG_PATH.exists():
        return fail(f"Missing config: {CONFIG_PATH}")

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for section, keys in REQUIRED_KEYS.items():
        if section not in data or not isinstance(data[section], dict):
            return fail(f"Missing section in config: {section}")
        missing = sorted(keys - set(data[section].keys()))
        if missing:
            return fail(f"Missing keys in config section {section}: {missing}")

    for file_path in TARGET_FILES:
        if not file_path.exists():
            return fail(f"Missing target file: {file_path}")
        text = file_path.read_text(encoding="utf-8")
        if "get_v1_params" not in text:
            return fail(f"File does not use shared v1 config: {file_path}")
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                return fail(f"Found forbidden hardcoded snippet '{snippet}' in {file_path}")

    print("v1 config usage validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
