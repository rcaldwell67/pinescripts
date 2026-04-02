from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_V6_PARAMS: dict[str, Any] = {
    "signal": {
        "ema_fast": 21,
        "ema_mid": 50,
        "ema_slow": 200,
        "ema_slope_lookback": 3,
        "adx_threshold": 15,
        "adx_slope_bars": 0,
        "di_spread": 0.0,
        "rsi_len": 14,
        "rsi_long_min": 42,
        "rsi_long_max": 68,
        "rsi_short_min": 32,
        "rsi_short_max": 58,
        "pullback_tolerance_pct": 0.30,
        "momentum_bars": 5,
        "volume_sma_len": 20,
        "volume_mult_min": 0.70,
        "bb_filter_enabled": False,
        "bb_len": 20,
        "bb_std_mult": 2.0,
        "bb_width_pct_min": 1.0,
        "donchian_filter_enabled": False,
        "donchian_len": 20,
        "min_body_atr_mult": 0.15,
        "atr_len": 14,
        "atr_baseline_len": 60,
        "atr_floor_pct": 0.10,
        "panic_suppression_mult": 1.5,
        "session_filter_enabled": True,
        "session_start_hour_et": 9,
        "session_end_hour_et": 14,
        "macro_ema_period": 0,
        "enable_longs": True,
        "enable_shorts": True,
    },
    "risk": {
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 6.0,
        "trail_activate_atr_mult": 2.5,
        "trail_dist_atr_mult": 0.1,
        "risk_pct": 3.0,
        "max_bars_in_trade": 30,
        "initial_equity": 1000.0,
    },
    "portfolio": {
        "min_adx": 14.0,
        "min_volume_ratio": 0.35,
        "min_atr_pct": 0.08,
        "weak_regime_min_score": 3,
        "weak_regime_risk_multiplier": 0.75,
        "strong_regime_risk_multiplier": 1.0,
        "crypto_risk_multiplier": 0.9,
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
    return Path(__file__).resolve().parent / "configs" / "v6_runtime.json"


def _normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def get_v6_params(
    config_path: str | Path | None = None,
    symbol: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    path = Path(config_path) if config_path else _default_config_path()
    if not path.exists():
        return DEFAULT_V6_PARAMS

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return DEFAULT_V6_PARAMS

    loaded = dict(loaded)
    profiles = loaded.get("profiles")
    if profile and isinstance(profiles, dict):
        profile_cfg = profiles.get(profile)
        if isinstance(profile_cfg, dict):
            loaded = _deep_merge(loaded, profile_cfg)

    symbol_overrides = loaded.get("symbol_overrides")
    if isinstance(symbol_overrides, dict):
        loaded.pop("symbol_overrides", None)
    loaded.pop("profiles", None)

    merged = _deep_merge(DEFAULT_V6_PARAMS, loaded)

    if symbol and isinstance(symbol_overrides, dict):
        override = symbol_overrides.get(_normalize_symbol(symbol))
        if isinstance(override, dict):
            merged = _deep_merge(merged, override)

    return merged
