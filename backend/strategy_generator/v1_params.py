from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_V1_PARAMS: dict[str, Any] = {
    "signal": {
        "ema_fast": 21,
        "ema_mid": 50,
        "ema_slow": 200,
        "ema_slope_lookback": 3,
        "rsi_len": 14,
        "rsi_short_min": 30,
        "rsi_short_max": 58,
        "pullback_tolerance_pct": 0.40,
        "volume_sma_len": 20,
        "volume_mult_min": 0.30,
        "min_body_atr_mult": 0.15,
        "atr_len": 14,
        "atr_floor_pct": 0.10,
    },
    "risk": {
        "sl_atr_mult": 4.0,
        "tp_atr_mult": 8.0,
        "trail_activate_atr_mult": 3.5,
        "trail_dist_atr_mult": 0.1,
        "risk_pct": 2.0,
        "max_bars_in_trade": 100,
        "initial_equity": 100000.0,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "configs" / "v1_runtime.json"


def get_v1_params(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else _default_config_path()
    if not path.exists():
        return DEFAULT_V1_PARAMS

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return DEFAULT_V1_PARAMS

    return _deep_merge(DEFAULT_V1_PARAMS, loaded)
