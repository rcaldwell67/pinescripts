from __future__ import annotations

def get_universal_params(symbol: str = None, profile: str = None) -> dict:
    """
    Returns default parameters for the universal APM strategy.
    """
    return {
        "signal": {
            "ema_fast": 21,
            "ema_mid": 50,
            "ema_slow": 200,
            "ema_slope_lookback": 3,
            "ema_slope_min": 0.0,
            "adx_threshold": 20,
            "adx_len": 14,
            "pullback_tolerance_pct": 0.20,
            "rsi_len": 14,
            "rsi_long_min": 42,
            "rsi_long_max": 72,
            "rsi_short_min": 32,
            "rsi_short_max": 58,
            "volume_sma_len": 20,
            "volume_mult": 1.2,
            "min_body_atr_mult": 0.20,
            "atr_len": 14,
            "atr_baseline_len": 60,
            "atr_floor_pct": 0.10,
            "panic_suppression_mult": 1.5,
            "session_filter_enabled": True,
            "session_start_hour_et": 9,
            "session_end_hour_et": 14,
        },
        "risk": {
            "sl_atr_mult": 2.0,
            "tp_atr_mult": 3.0,
            "trail_activate_atr_mult": 2.0,
            "trail_dist_atr_mult": 0.5,
            "risk_pct": 1.0,
            "max_bars_in_trade": 25,
            "initial_equity": 10000.0,
        }
    }
