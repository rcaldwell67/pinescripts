"""
APM Universal Backtest (Python)
Implements the universal Pine Script logic for use with Backtrader and the main backtest runner.
"""
import pandas as pd
import numpy as np

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
    tr = pd.concat([
        (df['High'] - df['Low']).abs(),
        (df['High'] - prev_close).abs(),
        (df['Low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()

def backtest_apm_universal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    signal = params["signal"]
    risk = params["risk"]

    # Indicator calculations
    df = df.copy()
    df['ema_fast'] = ema(df['Close'], int(signal['ema_fast']))
    df['ema_mid'] = ema(df['Close'], int(signal['ema_mid']))
    df['ema_slow'] = ema(df['Close'], int(signal['ema_slow']))
    df['rsi'] = rsi(df['Close'], int(signal['rsi_len']))
    df['atr'] = atr(df, int(signal['atr_len']))
    df['atr_baseline'] = df['atr'].rolling(int(signal['atr_baseline_len'])).mean()
    df['vol_sma'] = df['Volume'].rolling(int(signal['volume_sma_len'])).mean()

    # Entry logic
    long_entries = []
    short_entries = []
    for i in range(max(int(signal['ema_slow']), int(signal['ema_slope_lookback']) + 1), len(df)):
        # Trend filters
        trend_long = df['ema_fast'].iloc[i] > df['ema_mid'].iloc[i] > df['ema_slow'].iloc[i]
        trend_short = df['ema_fast'].iloc[i] < df['ema_mid'].iloc[i] < df['ema_slow'].iloc[i]
        # EMA slope
        ema_slope = (df['ema_fast'].iloc[i] - df['ema_fast'].iloc[i - int(signal['ema_slope_lookback'])]) / df['ema_fast'].iloc[i - int(signal['ema_slope_lookback'])] * 100
        ema_slope_ok_long = not signal.get('ema_slope', True) or ema_slope > signal.get('ema_slope_min', 0.0)
        ema_slope_ok_short = not signal.get('ema_slope', True) or ema_slope < -signal.get('ema_slope_min', 0.0)
        # RSI
        rsi_long_ok = df['rsi'].iloc[i] > signal['rsi_long_min'] and df['rsi'].iloc[i] < signal['rsi_long_max'] and df['rsi'].iloc[i] > df['rsi'].iloc[i-1]
        rsi_short_ok = df['rsi'].iloc[i] > signal['rsi_short_min'] and df['rsi'].iloc[i] < signal['rsi_short_max'] and df['rsi'].iloc[i] < df['rsi'].iloc[i-1]
        # Volume
        vol_ok = df['Volume'].iloc[i] > df['vol_sma'].iloc[i] * signal['volume_mult']
        # Body
        body = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
        body_ok = body > df['atr'].iloc[i] * signal['min_body_atr_mult']
        # ATR
        atr_ok = df['atr'].iloc[i] / df['Close'].iloc[i] > signal['atr_floor_pct'] / 100
        # Panic
        panic_ok = df['atr'].iloc[i] < df['atr_baseline'].iloc[i] * signal['panic_suppression_mult']
        # Session
        sess_ok = True
        if signal.get('session_filter_enabled', True):
            if 'timestamp' in df.columns:
                ts = pd.to_datetime(df['timestamp'].iloc[i], utc=True, errors='coerce')
                hour = ts.tz_convert('America/New_York').hour if pd.notna(ts) else np.nan
                sess_ok = pd.notna(hour) and signal['session_start_hour_et'] <= hour < signal['session_end_hour_et']
        # Pullback
        pb_long = df['Low'].iloc[i-1] <= df['ema_fast'].iloc[i-1] * (1 + signal['pullback_tolerance_pct'] / 100) and df['Close'].iloc[i] > df['ema_fast'].iloc[i]
        pb_short = df['High'].iloc[i-1] >= df['ema_fast'].iloc[i-1] * (1 - signal['pullback_tolerance_pct'] / 100) and df['Close'].iloc[i] < df['ema_fast'].iloc[i]

        if trend_long and ema_slope_ok_long and rsi_long_ok and vol_ok and body_ok and atr_ok and panic_ok and sess_ok and pb_long:
            long_entries.append(i)
        if trend_short and ema_slope_ok_short and rsi_short_ok and vol_ok and body_ok and atr_ok and panic_ok and sess_ok and pb_short:
            short_entries.append(i)

    # Trade simulation (simplified)
    equity = float(risk["initial_equity"])
    trades = []
    open_until = -1
    sl_mult = float(risk["sl_atr_mult"])
    tp_mult = float(risk["tp_atr_mult"])
    trail_activate_mult = float(risk["trail_activate_atr_mult"])
    trail_dist_mult = float(risk["trail_dist_atr_mult"])
    risk_pct = float(risk["risk_pct"])
    max_bars = int(risk["max_bars_in_trade"])

    for i in long_entries + short_entries:
        if i <= open_until:
            continue
        entry_price = df['Close'].iloc[i]
        atr_val = df['atr'].iloc[i]
        if pd.isna(atr_val) or atr_val <= 0:
            continue
        side = 'long' if i in long_entries else 'short'
        if side == 'long':
            sl = entry_price - sl_mult * atr_val
            tp = entry_price + tp_mult * atr_val
        else:
            sl = entry_price + sl_mult * atr_val
            tp = entry_price - tp_mult * atr_val
        trail_active = False
        best_price = entry_price
        qty = equity * risk_pct / 100 / abs(sl - entry_price) if abs(sl - entry_price) > 0 else 0
        exit_price = None
        exit_type = None
        trade_end = len(df) if max_bars <= 0 else min(i + max_bars, len(df))
        for j in range(i+1, trade_end):
            price = df['Close'].iloc[j]
            if not trail_active:
                if (side == 'long' and price > entry_price + trail_activate_mult * atr_val) or (side == 'short' and price < entry_price - trail_activate_mult * atr_val):
                    trail_active = True
                    best_price = price
            if trail_active:
                if side == 'long':
                    best_price = max(best_price, price)
                    trail_stop = best_price - trail_dist_mult * atr_val
                    if price < trail_stop:
                        exit_price = trail_stop
                        exit_type = 'trailing_stop'
                        break
                else:
                    best_price = min(best_price, price)
                    trail_stop = best_price + trail_dist_mult * atr_val
                    if price > trail_stop:
                        exit_price = trail_stop
                        exit_type = 'trailing_stop'
                        break
            if side == 'long':
                if price <= sl:
                    exit_price = sl
                    exit_type = 'stop_loss'
                    break
                if price >= tp:
                    exit_price = tp
                    exit_type = 'take_profit'
                    break
            else:
                if price >= sl:
                    exit_price = sl
                    exit_type = 'stop_loss'
                    break
                if price <= tp:
                    exit_price = tp
                    exit_type = 'take_profit'
                    break
        if exit_price is None and trade_end < len(df):
            exit_price = df['Close'].iloc[trade_end-1]
            exit_type = 'max_bars'
        if exit_price is not None:
            dollar_pnl = (exit_price - entry_price) * qty if side == 'long' else (entry_price - exit_price) * qty
            equity += dollar_pnl
            trades.append({
                'entry_idx': i,
                'exit_idx': trade_end-1 if exit_price is not None else None,
                'entry': entry_price,
                'exit': exit_price,
                'side': side,
                'pnl': dollar_pnl,
                'equity': equity,
                'exit_type': exit_type,
            })
            open_until = trade_end-1
    return pd.DataFrame(trades)
