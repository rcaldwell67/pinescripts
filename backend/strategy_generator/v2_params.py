from __future__ import annotations

from typing import Any


DEFAULT_V2_PARAMS: dict[str, Any] = {
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
        "min_body_atr_mult": 0.15,
        "atr_len": 14,
        "atr_baseline_len": 60,
        "atr_floor_pct": 0.10,
        "panic_suppression_mult": 1.5,
        "session_filter_enabled": True,
        "session_start_hour_et": 9,
        "session_end_hour_et": 14,
        "macro_ema_period": 0,
        "enable_longs": False,
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
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def get_v2_params(symbol: str | None = None, profile: str | None = None) -> dict[str, Any]:
    # Hook kept for parity with v1; symbol/profile overrides can be added later.
    _ = symbol
    _ = profile
    return _deep_merge(DEFAULT_V2_PARAMS, {})
