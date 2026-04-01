"""Adaptive Pullback Momentum v1.0-5m signal engine."""

import numpy as np
import pandas as pd

from v1_params import get_v1_params

# Helper functions for indicators
def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def rsi(series, length):
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(100.0)


def atr(df, length):
    prev_close = df['Close'].shift(1)
    tr = pd.concat(
        [
            (df['High'] - df['Low']).abs(),
            (df['High'] - prev_close).abs(),
            (df['Low'] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def dmi(df, length):
    high = df['High']
    low = df['Low']
    close = df['Close']

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_rma = tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean() / atr_rma
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean() / atr_rma
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    return plus_di, minus_di, adx, atr_rma


def _prepare_signal_frame(df, params):
    signal = params["signal"]

    ema_fast = int(signal["ema_fast"])
    ema_mid = int(signal["ema_mid"])
    ema_slow = int(signal["ema_slow"])
    rsi_len = int(signal["rsi_len"])
    atr_len = int(signal["atr_len"])
    atr_baseline_len = int(signal.get("atr_baseline_len", 60))
    volume_sma_len = int(signal["volume_sma_len"])
    macro_ema_period = int(signal.get("macro_ema_period", 0))

    df['ema21'] = ema(df['Close'], ema_fast)
    df['ema50'] = ema(df['Close'], ema_mid)
    df['ema200'] = ema(df['Close'], ema_slow)
    df['rsi'] = rsi(df['Close'], rsi_len)
    df['plus_di'], df['minus_di'], df['adx'], df['atr'] = dmi(df, atr_len)
    df['atr_baseline'] = df['atr'].rolling(atr_baseline_len).mean()
    df['vol_sma'] = df['Volume'].rolling(volume_sma_len).mean()
    if macro_ema_period > 0:
        df['macro_ema'] = ema(df['Close'], macro_ema_period)
    else:
        df['macro_ema'] = np.nan

    timestamps = pd.to_datetime(df.get('timestamp'), utc=True, errors='coerce')
    if timestamps is not None:
        try:
            et_hours = timestamps.dt.tz_convert('America/New_York').dt.hour
        except AttributeError:
            et_hours = pd.Series(np.nan, index=df.index)
    else:
        et_hours = pd.Series(np.nan, index=df.index)

    return signal, timestamps, et_hours


def _evaluate_short_entry_at(df, i, signal, et_hours):
    slope_lookback = int(signal["ema_slope_lookback"])
    adx_threshold = float(signal.get("adx_threshold", 15))
    adx_slope_bars = int(signal.get("adx_slope_bars", 0))
    di_spread = float(signal.get("di_spread", 0.0))
    rsi_short_min = float(signal["rsi_short_min"])
    rsi_short_max = float(signal["rsi_short_max"])
    pb_tol_pct = float(signal["pullback_tolerance_pct"])
    momentum_bars = int(signal.get("momentum_bars", 5))
    volume_mult_min = float(signal["volume_mult_min"])
    min_body_atr_mult = float(signal["min_body_atr_mult"])
    atr_floor_pct = float(signal["atr_floor_pct"])
    panic_suppression_mult = float(signal.get("panic_suppression_mult", 1.5))
    session_filter_enabled = bool(signal.get("session_filter_enabled", True))
    session_start_hour_et = int(signal.get("session_start_hour_et", 9))
    session_end_hour_et = int(signal.get("session_end_hour_et", 14))
    macro_ema_period = int(signal.get("macro_ema_period", 0))

    passed_stage = "start"
    if not (df['ema21'].iloc[i] < df['ema50'].iloc[i] < df['ema200'].iloc[i]):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "bearish_stack", "detail": "failed bearish_stack: ema21 < ema50 < ema200 required"}
    passed_stage = "bearish_stack"

    if not (df['ema21'].iloc[i] < df['ema21'].iloc[i - slope_lookback]):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "ema_slope", "detail": "failed ema_slope: ema21 must be falling over lookback"}
    passed_stage = "ema_slope"

    if not pd.notna(df['adx'].iloc[i]) or df['adx'].iloc[i] <= adx_threshold:
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "adx", "detail": f"failed adx: adx must exceed {adx_threshold:g}"}
    if adx_slope_bars > 0 and not (df['adx'].iloc[i] > df['adx'].iloc[i - adx_slope_bars]):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "adx_slope", "detail": "failed adx_slope: adx must be rising"}
    passed_stage = "adx"

    if di_spread > 0 and not ((df['minus_di'].iloc[i] - df['plus_di'].iloc[i]) >= di_spread):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "di_spread", "detail": f"failed di_spread: minus_di - plus_di must be >= {di_spread:g}"}
    passed_stage = "di_spread"

    if not (df['rsi'].iloc[i] < df['rsi'].iloc[i - 1]):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "rsi_falling", "detail": "failed rsi_falling: rsi must be lower than prior bar"}
    passed_stage = "rsi_falling"

    if momentum_bars > 0 and not (df['Close'].iloc[i] < df['Close'].iloc[i - momentum_bars]):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "momentum", "detail": f"failed momentum: close must be below close {momentum_bars} bars ago"}
    passed_stage = "momentum"

    pb_tol = df['ema21'].iloc[i - 1] * (1 - (pb_tol_pct / 100.0))
    body = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
    if not (
        df['High'].iloc[i - 1] >= pb_tol
        and df['Close'].iloc[i] < df['ema21'].iloc[i]
        and df['Close'].iloc[i] < df['Open'].iloc[i]
        and body >= min_body_atr_mult * df['atr'].iloc[i]
    ):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "pullback_break", "detail": "failed pullback_break: pullback touch and bearish break conditions not met"}
    passed_stage = "pullback_break"

    if not (rsi_short_min <= df['rsi'].iloc[i] <= rsi_short_max):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "rsi_range", "detail": f"failed rsi_range: rsi must be between {rsi_short_min:g} and {rsi_short_max:g}"}
    passed_stage = "rsi_range"

    if not (df['Volume'].iloc[i] >= volume_mult_min * df['vol_sma'].iloc[i]):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "volume", "detail": f"failed volume: volume must be >= {volume_mult_min:g}x vol_sma"}
    passed_stage = "volume"

    if not (df['atr'].iloc[i] / df['Close'].iloc[i] * 100 >= atr_floor_pct):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "atr_floor", "detail": f"failed atr_floor: atr% must be >= {atr_floor_pct:g}"}
    passed_stage = "atr_floor"

    if pd.notna(df['atr_baseline'].iloc[i]) and df['atr'].iloc[i] > df['atr_baseline'].iloc[i] * panic_suppression_mult:
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "panic", "detail": "failed panic: atr exceeds panic suppression threshold"}
    passed_stage = "panic"

    if session_filter_enabled:
        hour = et_hours.iloc[i]
        if not pd.notna(hour) or not (session_start_hour_et <= hour < session_end_hour_et):
            return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "session", "detail": f"failed session: ET hour must be in [{session_start_hour_et}, {session_end_hour_et})"}
    passed_stage = "session"

    if macro_ema_period > 0 and not (df['Close'].iloc[i] < df['macro_ema'].iloc[i]):
        return {"is_entry": False, "passed_stage": passed_stage, "failed_stage": "macro", "detail": "failed macro: close must be below macro_ema"}

    return {"is_entry": True, "passed_stage": "macro", "failed_stage": None, "detail": "latest bar qualifies as an entry"}


def apm_v1_latest_bar_analysis(df, params=None):
    params = params or get_v1_params()
    signal, timestamps, et_hours = _prepare_signal_frame(df, params)
    slope_lookback = int(signal["ema_slope_lookback"])
    momentum_bars = int(signal.get("momentum_bars", 5))
    adx_slope_bars = int(signal.get("adx_slope_bars", 0))
    ema_slow = int(signal["ema_slow"])
    start_idx = max(ema_slow, slope_lookback + 1, momentum_bars, adx_slope_bars)

    latest_ts = None
    if len(df) > 0 and timestamps is not None and len(timestamps) == len(df):
        latest_val = timestamps.iloc[-1]
        latest_ts = latest_val.isoformat() if pd.notna(latest_val) else None

    if len(df) <= start_idx:
        return {
            "is_entry": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "insufficient_history",
            "detail": f"insufficient_history: need > {start_idx} bars, have {len(df)}",
            "latest_bar_ts": latest_ts,
        }

    result = _evaluate_short_entry_at(df, len(df) - 1, signal, et_hours)
    result["latest_bar_ts"] = latest_ts
    result["is_near_miss"] = bool(not result["is_entry"] and result["passed_stage"] != "start")
    return result


def apm_v1_latest_bar_exit_analysis(df, side="short", params=None):
    params = params or get_v1_params()
    signal, timestamps, _et_hours = _prepare_signal_frame(df, params)
    slope_lookback = int(signal["ema_slope_lookback"])
    momentum_bars = int(signal.get("momentum_bars", 5))
    adx_slope_bars = int(signal.get("adx_slope_bars", 0))
    ema_slow = int(signal["ema_slow"])
    start_idx = max(ema_slow, slope_lookback + 1, momentum_bars, adx_slope_bars)

    latest_ts = None
    if len(df) > 0 and timestamps is not None and len(timestamps) == len(df):
        latest_val = timestamps.iloc[-1]
        latest_ts = latest_val.isoformat() if pd.notna(latest_val) else None

    if len(df) <= start_idx:
        return {
            "is_exit": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "insufficient_history",
            "detail": f"insufficient_history: need > {start_idx} bars, have {len(df)}",
            "latest_bar_ts": latest_ts,
        }

    i = len(df) - 1
    close = float(df['Close'].iloc[i])
    ema21 = float(df['ema21'].iloc[i])
    ema50 = float(df['ema50'].iloc[i])
    rsi_val = float(df['rsi'].iloc[i])

    # Exit model: require a fast-EMA reversal trigger and RSI confirmation.
    # This keeps exits directional and avoids using entry signals as an exit proxy.
    if side == "long":
        if not (close < ema21):
            return {
                "is_exit": False,
                "is_near_miss": False,
                "passed_stage": "start",
                "failed_stage": "reversal_trigger",
                "detail": "failed reversal_trigger: close must be below ema21 for long exit",
                "latest_bar_ts": latest_ts,
            }
        if not (rsi_val <= 50):
            return {
                "is_exit": False,
                "is_near_miss": True,
                "passed_stage": "reversal_trigger",
                "failed_stage": "rsi_confirm",
                "detail": "failed rsi_confirm: rsi must be <= 50 for long exit",
                "latest_bar_ts": latest_ts,
            }
        return {
            "is_exit": True,
            "is_near_miss": False,
            "passed_stage": "rsi_confirm",
            "failed_stage": None,
            "detail": "latest bar qualifies as a long exit",
            "latest_bar_ts": latest_ts,
        }

    if not (close > ema21):
        return {
            "is_exit": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "reversal_trigger",
            "detail": "failed reversal_trigger: close must be above ema21 for short exit",
            "latest_bar_ts": latest_ts,
        }
    if not (rsi_val >= 50 or close > ema50):
        return {
            "is_exit": False,
            "is_near_miss": True,
            "passed_stage": "reversal_trigger",
            "failed_stage": "rsi_or_ema50_confirm",
            "detail": "failed rsi_or_ema50_confirm: need rsi >= 50 or close > ema50 for short exit",
            "latest_bar_ts": latest_ts,
        }
    return {
        "is_exit": True,
        "is_near_miss": False,
        "passed_stage": "rsi_or_ema50_confirm",
        "failed_stage": None,
        "detail": "latest bar qualifies as a short exit",
        "latest_bar_ts": latest_ts,
    }

# Main strategy logic
def apm_v1_signals(df, params=None):
    params = params or get_v1_params()
    signal, _timestamps, et_hours = _prepare_signal_frame(df, params)
    ema_slow = int(signal["ema_slow"])
    slope_lookback = int(signal["ema_slope_lookback"])
    momentum_bars = int(signal.get("momentum_bars", 5))
    adx_slope_bars = int(signal.get("adx_slope_bars", 0))

    # Entry logic (shorts only)
    entries = []
    start_idx = max(ema_slow, slope_lookback + 1, momentum_bars, adx_slope_bars)
    for i in range(start_idx, len(df)):
        if _evaluate_short_entry_at(df, i, signal, et_hours)["is_entry"]:
            entries.append(i)
    return entries

# Example usage (requires OHLCV DataFrame 'df')
# entries = apm_v1_signals(df)
# print(entries)
