import sys
import json
import os
from pathlib import Path
from add_symbol_to_db import add_symbol

# Template config (matches best-performing symbols)
TEMPLATE_CONFIG = {
    "signal": {
        "enable_longs": True,
        "enable_shorts": True,
        "pullback_tolerance_pct": 0.2,
        "momentum_bars": 8,
        "rsi_long_min": 44,
        "rsi_long_max": 58,
        "rsi_short_min": 32,
        "rsi_short_max": 52,
        "adx_slope_bars": 2,
        "adx_threshold": 16,
        "di_spread": 5.0,
        "session_filter_enabled": True,
        "session_start_hour_et": 9,
        "session_end_hour_et": 15,
        "volume_mult_min": 0.9,
        "min_body_atr_mult": 0.15,
        "atr_floor_pct": 0.12,
        "panic_suppression_mult": 2.0,
        "bb_filter_enabled": False,
        "donchian_filter_enabled": False
    },
    "risk": {
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 6.0,
        "trail_activate_atr_mult": 2.0,
        "trail_dist_atr_mult": 0.08,
        "risk_pct": 1.5,
        "max_bars_in_trade": 20
    }
}

CONFIG_PATH = Path(__file__).resolve().parent.parent / "backend/strategy_generator/configs/v7_runtime.json"

def add_symbol_and_config(symbol, description=None):
    # Add symbol as disabled
    add_symbol(symbol, description)
    # Add config override
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    overrides = config.get("symbol_overrides", {})
    overrides[symbol] = TEMPLATE_CONFIG
    config["symbol_overrides"] = overrides
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Config override for {symbol} added to v7_runtime.json.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_symbol_and_config.py SYMBOL [DESCRIPTION]")
        sys.exit(1)
    symbol = sys.argv[1]
    description = sys.argv[2] if len(sys.argv) > 2 else None
    add_symbol_and_config(symbol, description)
