from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(SG_DIR))

from v2_params import DEFAULT_V2_PARAMS  # noqa: E402

REQUIRED_KEYS = {
    "signal": {
        "ema_fast",
        "ema_mid",
        "ema_slow",
        "ema_slope_lookback",
        "rsi_len",
        "rsi_long_min",
        "rsi_long_max",
        "rsi_short_min",
        "rsi_short_max",
        "pullback_tolerance_pct",
        "volume_sma_len",
        "volume_mult_min",
        "min_body_atr_mult",
        "atr_len",
        "atr_floor_pct",
        "enable_longs",
        "enable_shorts",
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
    REPO_ROOT / "backend" / "strategy_generator" / "apm_v2.py",
    REPO_ROOT / "backend" / "strategy_generator" / "apm_v2_backtest.py",
    REPO_ROOT / "backend" / "backtest_backtrader_alpaca.py",
    REPO_ROOT / "backend" / "paper_trading" / "realtime_alpaca_paper_trader.py",
    REPO_ROOT / "backend" / "live_trading" / "realtime_alpaca_live_trader.py",
]

REQUIRED_SNIPPETS = {
    str(REPO_ROOT / "backend" / "strategy_generator" / "apm_v2.py"): ["get_v2_params"],
    str(REPO_ROOT / "backend" / "strategy_generator" / "apm_v2_backtest.py"): ["get_v2_params"],
    str(REPO_ROOT / "backend" / "backtest_backtrader_alpaca.py"): ["version == \"v2\"", "get_v2_params"],
    str(REPO_ROOT / "backend" / "paper_trading" / "realtime_alpaca_paper_trader.py"): ["get_v2_params", "version == \"v2\""],
    str(REPO_ROOT / "backend" / "live_trading" / "realtime_alpaca_live_trader.py"): ["get_v2_params", "version == \"v2\""],
}


def fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    for section, keys in REQUIRED_KEYS.items():
        if section not in DEFAULT_V2_PARAMS or not isinstance(DEFAULT_V2_PARAMS[section], dict):
            return fail(f"Missing section in DEFAULT_V2_PARAMS: {section}")
        missing = sorted(keys - set(DEFAULT_V2_PARAMS[section].keys()))
        if missing:
            return fail(f"Missing keys in v2 params section {section}: {missing}")

    for file_path in TARGET_FILES:
        if not file_path.exists():
            return fail(f"Missing target file: {file_path}")
        text = file_path.read_text(encoding="utf-8")
        for snippet in REQUIRED_SNIPPETS.get(str(file_path), []):
            if snippet not in text:
                return fail(f"Missing required snippet '{snippet}' in {file_path}")

    print("v2 config usage validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
