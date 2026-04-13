from __future__ import annotations

from typing import Any

from apm_v1 import apm_v1_latest_bar_analysis, apm_v1_latest_bar_exit_analysis, apm_v1_signals
from v6_params import get_v6_params


def apm_v6_signals(df, side: str = "short", params: dict[str, Any] | None = None):
    cfg = params or get_v6_params()
    signal = cfg.get("signal", {})
    # --- Regime filter parameters ---
    regime_filter_enabled = bool(signal.get("regime_filter_enabled", False))
    min_regime_score = float(signal.get("min_regime_score", 2.0))
    min_adx = float(signal.get("min_adx", 14.0))
    min_volume_ratio = float(signal.get("min_volume_ratio", 0.35))
    min_atr_pct = float(signal.get("min_atr_pct", 0.08))
    if side == "long" and not bool(signal.get("enable_longs", False)):
        return []
    if side == "short" and not bool(signal.get("enable_shorts", True)):
        return []

    # --- Standalone v6 entry logic (no v1 gates) ---
    donchian_len = int(signal.get('donchian_len', 20))
    bb_len = int(signal.get('bb_len', 20))
    bb_std_mult = float(signal.get('bb_std_mult', 2.0))
    df['donchian_high'] = df['High'].rolling(donchian_len).max()
    df['donchian_low'] = df['Low'].rolling(donchian_len).min()
    df['bb_mid'] = df['Close'].rolling(bb_len).mean()
    bb_std = df['Close'].rolling(bb_len).std()
    df['bb_upper'] = df['bb_mid'] + (bb_std_mult * bb_std)
    df['bb_lower'] = df['bb_mid'] - (bb_std_mult * bb_std)
    entries = []
    last_entry_idx = -1000
    cooldown_bars = 10
    # --- Volatility filter parameters ---
    atr_percentile_filter_enabled = bool(signal.get("atr_percentile_filter_enabled", False))
    atr_percentile_min = float(signal.get("atr_percentile_min", 0.0))
    atr_percentile_max = float(signal.get("atr_percentile_max", 100.0))
    # --- Trend filter parameters ---
    ema_trend_filter_enabled = bool(signal.get("ema_trend_filter_enabled", False))
    ema_trend_lookback = int(signal.get("ema_trend_lookback", 10))
    ema_trend_type = signal.get("ema_trend_type", "ema21")

    for i in range(max(donchian_len, bb_len, ema_trend_lookback), len(df)):
        if i - last_entry_idx < cooldown_bars:
            continue
        price = df['Close'].iloc[i]
        donchian_break = price > df['donchian_high'].iloc[i-1] if side == "long" else price < df['donchian_low'].iloc[i-1]
        bb_break = price > df['bb_upper'].iloc[i-1] if side == "long" else price < df['bb_lower'].iloc[i-1]
        rsi = df['rsi'].iloc[i] if 'rsi' in df.columns else None
        mr_entry = False
        if side == "long" and rsi is not None:
            mr_entry = rsi < 55
        elif side == "short" and rsi is not None:
            mr_entry = rsi > 45

        # --- Regime filter: require minimum market regime score ---
        if regime_filter_enabled:
            regime_score = 0
            # ADX regime
            if 'adx' in df.columns and pd.notna(df['adx'].iloc[i]) and df['adx'].iloc[i] >= min_adx:
                regime_score += 1
            # ATR regime (as percent of price)
            if 'atr' in df.columns and df['atr'].iloc[i] / price >= min_atr_pct:
                regime_score += 1
            # Volume regime
            if 'vol_sma' in df.columns and df['vol_sma'].iloc[i] > 0 and df['Volume'].iloc[i] / df['vol_sma'].iloc[i] >= min_volume_ratio:
                regime_score += 1
            if regime_score < min_regime_score:
                continue

        # --- Volatility filter: ATR percentile ---
        if atr_percentile_filter_enabled:
            atr_pctile = df['atr_pctile'].iloc[i] if 'atr_pctile' in df.columns else None
            if not (atr_pctile is not None and atr_percentile_min <= atr_pctile <= atr_percentile_max):
                continue

        # --- Trend filter: EMA rising/falling ---
        if ema_trend_filter_enabled:
            ema = df[ema_trend_type].iloc[i]
            ema_prev = df[ema_trend_type].iloc[i - ema_trend_lookback]
            if side == "long" and not (ema > ema_prev):
                continue
            if side == "short" and not (ema < ema_prev):
                continue

        if donchian_break or bb_break or mr_entry:
            entries.append(i)
            last_entry_idx = i
    return entries

def apm_v6_dynamic_trailing_stop(entry_price, current_price, atr, base_trail=2.0, profit_trail=1.0):
    """
    Dynamic trailing stop: base_trail ATR below entry, tightens to profit_trail ATR below current price if in profit.
    """
    stop = entry_price - base_trail * atr
    if current_price > entry_price:
        stop = max(stop, current_price - profit_trail * atr)
    return stop


def apm_v6_latest_bar_analysis(df, side: str = "short", params: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = params or get_v6_params()
    signal = cfg.get("signal", {})
    if side == "long" and not bool(signal.get("enable_longs", False)):
        return {
            "is_entry": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "disabled",
            "detail": "long side disabled in v6 params",
            "latest_bar_ts": None,
        }
    if side == "short" and not bool(signal.get("enable_shorts", True)):
        return {
            "is_entry": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "disabled",
            "detail": "short side disabled in v6 params",
            "latest_bar_ts": None,
        }
    return apm_v1_latest_bar_analysis(df, side=side, params=cfg)


def apm_v6_latest_bar_exit_analysis(df, side: str = "short", params: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = params or get_v6_params()
    return apm_v1_latest_bar_exit_analysis(df, side=side, params=cfg)
