# --- v7 parameter loader ---
def get_v7_params(symbol: str):
    # Example: load default parameters for v7; customize as needed
    # In production, load from DB, JSON, or symbol-specific config
    return {
        "signal": {
            "ema_fast": 8,
            "ema_mid": 21,
            "ema_slow": 55,
            "rsi_len": 14,
            "atr_len": 14,
            "atr_baseline_len": 100,
            "volume_sma_len": 20,
        }
    }
"""
APM v7 signal engine (unified v1–v6 logic, all timespans, symbol-specific).
This script is a template for symbol-specific v7 strategies.
"""
import numpy as np
import pandas as pd

# --- Universal indicator functions (from v1-v6) ---
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

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def stoch_kd(df, k_len=14, d_len=3):
    low_min = df['Low'].rolling(window=k_len, min_periods=1).min()
    high_max = df['High'].rolling(window=k_len, min_periods=1).max()
    k = 100 * (df['Close'] - low_min) / (high_max - low_min + 1e-9)
    d = k.rolling(window=d_len, min_periods=1).mean()
    return k, d

def cci(df, n=20):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    ma = tp.rolling(n, min_periods=1).mean()
    md = tp.rolling(n, min_periods=1).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    cci_val = (tp - ma) / (0.015 * md + 1e-9)
    return cci_val

# --- v7 signal preparation (combines all v1–v6 features) ---
def supertrend(df, period=10, multiplier=3):
    atr_ = atr(df, period)
    hl2 = (df['High'] + df['Low']) / 2
    upperband = hl2 + (multiplier * atr_)
    lowerband = hl2 - (multiplier * atr_)
    supertrend = [np.nan] * len(df)
    direction = [True] * len(df)
    for i in range(period, len(df)):
        if df['Close'].iloc[i-1] <= upperband.iloc[i-1]:
            upperband.iloc[i] = min(upperband.iloc[i], upperband.iloc[i-1])
        if df['Close'].iloc[i-1] >= lowerband.iloc[i-1]:
            lowerband.iloc[i] = max(lowerband.iloc[i], lowerband.iloc[i-1])
        if df['Close'].iloc[i] > upperband.iloc[i-1]:
            direction[i] = True
        elif df['Close'].iloc[i] < lowerband.iloc[i-1]:
            direction[i] = False
        else:
            direction[i] = direction[i-1]
            if direction[i] and lowerband.iloc[i] < lowerband.iloc[i-1]:
                lowerband.iloc[i] = lowerband.iloc[i-1]
            if not direction[i] and upperband.iloc[i] > upperband.iloc[i-1]:
                upperband.iloc[i] = upperband.iloc[i-1]
        supertrend[i] = lowerband.iloc[i] if direction[i] else upperband.iloc[i]
    return pd.Series(supertrend, index=df.index)

def keltner_channel(df, length=20, mult=2):
    ema_ = ema(df['Close'], length)
    atr_ = atr(df, length)
    kc_upper = ema_ + mult * atr_
    kc_lower = ema_ - mult * atr_
    return kc_upper, kc_lower

def mfi(df, length=14):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    mf = tp * df['Volume']
    pos_mf = mf.where(tp > tp.shift(1), 0)
    neg_mf = mf.where(tp < tp.shift(1), 0)
    pos_sum = pos_mf.rolling(length).sum()
    neg_sum = neg_mf.rolling(length).sum()
    mfi_val = 100 - (100 / (1 + (pos_sum / (neg_sum + 1e-9))))
    return mfi_val

def tsi(series, r=25, s=13):
    diff = series.diff()
    abs_diff = diff.abs()
    double_smoothed = diff.ewm(span=r, adjust=False).mean().ewm(span=s, adjust=False).mean()
    double_smoothed_abs = abs_diff.ewm(span=r, adjust=False).mean().ewm(span=s, adjust=False).mean()
    tsi_val = 100 * double_smoothed / (double_smoothed_abs + 1e-9)
    return tsi_val

def wpr(df, length=14):
    highest_high = df['High'].rolling(length).max()
    lowest_low = df['Low'].rolling(length).min()
    wpr_val = -100 * (highest_high - df['Close']) / (highest_high - lowest_low + 1e-9)
    return wpr_val

def sar(df, af=0.02, max_af=0.2):
    sar = [df['Low'].iloc[0]]
    ep = df['High'].iloc[0]
    af_val = af
    long = True
    for i in range(1, len(df)):
        prev_sar = sar[-1]
        if long:
            sar.append(prev_sar + af_val * (ep - prev_sar))
            if df['Low'].iloc[i] < sar[-1]:
                long = False
                sar[-1] = ep
                ep = df['Low'].iloc[i]
                af_val = af
        else:
            sar.append(prev_sar + af_val * (ep - prev_sar))
            if df['High'].iloc[i] > sar[-1]:
                long = True
                sar[-1] = ep
                ep = df['High'].iloc[i]
                af_val = af
        if long:
            if df['High'].iloc[i] > ep:
                ep = df['High'].iloc[i]
                af_val = min(af_val + af, max_af)
        else:
            if df['Low'].iloc[i] < ep:
                ep = df['Low'].iloc[i]
                af_val = min(af_val + af, max_af)
    return pd.Series(sar, index=df.index)

def prepare_v7_signal_frame(df, params):
    # Calculate all indicators used in v1–v6 and new ones
    signal = params["signal"]
    df['ema_fast'] = ema(df['Close'], int(signal['ema_fast']))
    df['ema_mid'] = ema(df['Close'], int(signal['ema_mid']))
    df['ema_slow'] = ema(df['Close'], int(signal['ema_slow']))
    df['rsi'] = rsi(df['Close'], int(signal['rsi_len']))
    df['atr'] = atr(df, int(signal['atr_len']))
    df['atr_baseline'] = df['atr'].rolling(int(signal['atr_baseline_len'])).mean()
    df['vol_sma'] = df['Volume'].rolling(int(signal['volume_sma_len'])).mean()
    df['macd_line'], df['macd_signal_line'], df['macd_hist'] = macd(df['Close'])
    df['stoch_k'], df['stoch_d'] = stoch_kd(df)
    df['cci'] = cci(df)
    # New indicators
    df['supertrend'] = supertrend(df, period=int(signal.get('supertrend_period', 10)), multiplier=float(signal.get('supertrend_mult', 3)))
    df['kc_upper'], df['kc_lower'] = keltner_channel(df, length=int(signal.get('kc_len', 20)), mult=float(signal.get('kc_mult', 2)))
    df['mfi'] = mfi(df, length=int(signal.get('mfi_len', 14)))
    df['tsi'] = tsi(df['Close'], r=int(signal.get('tsi_r', 25)), s=int(signal.get('tsi_s', 13)))
    df['wpr'] = wpr(df, length=int(signal.get('wpr_len', 14)))
    df['sar'] = sar(df, af=float(signal.get('sar_af', 0.02)), max_af=float(signal.get('sar_max_af', 0.2)))
    return df

# --- Example entry/exit logic (to be customized per symbol) ---
def v7_entry_logic(df, i, params):
    signal = params["signal"]
    # Trend, momentum, volatility, and multi-factor confirmation
    trend_ok = df['ema_fast'].iloc[i] > df['ema_mid'].iloc[i] > df['ema_slow'].iloc[i]
    rsi_ok = 40 < df['rsi'].iloc[i] < 70
    macd_ok = df['macd_line'].iloc[i] > df['macd_signal_line'].iloc[i]
    stoch_ok = df['stoch_k'].iloc[i] > 20 and df['stoch_d'].iloc[i] > 20
    cci_ok = -100 < df['cci'].iloc[i] < 100
    # New indicators with enable toggles
    supertrend_ok = (not signal.get('enable_supertrend', False)) or (df['Close'].iloc[i] > df['supertrend'].iloc[i])
    kc_ok = (not signal.get('enable_kc', False)) or (df['Close'].iloc[i] > df['kc_upper'].iloc[i])
    mfi_ok = (not signal.get('enable_mfi', False)) or (df['mfi'].iloc[i] > 50)
    tsi_ok = (not signal.get('enable_tsi', False)) or (df['tsi'].iloc[i] > 0)
    wpr_ok = (not signal.get('enable_wpr', False)) or (df['wpr'].iloc[i] > -80)
    sar_ok = (not signal.get('enable_sar', False)) or (df['Close'].iloc[i] > df['sar'].iloc[i])
    # Require at least 3/5 classic factors and at least 2/6 new factors if enabled
    classic_factors = [trend_ok, rsi_ok, macd_ok, stoch_ok, cci_ok]
    new_factors = [supertrend_ok, kc_ok, mfi_ok, tsi_ok, wpr_ok, sar_ok]
    min_classic = 3
    min_new = 2 if any([signal.get(f'enable_{name}', False) for name in ['supertrend','kc','mfi','tsi','wpr','sar']]) else 0
    return (sum(classic_factors) >= min_classic) and (sum(new_factors) >= min_new)

# --- Main v7 backtest loop (all timespans) ---
def run_v7_backtest(df, params):
    df = prepare_v7_signal_frame(df, params)
    trades = []
    equity = 100000.0
    open_until = -1
    max_bars = 50  # Example: max bars in trade
    for i in range(max(200, int(params['signal']['ema_slow'])), len(df)):
        if i <= open_until:
            continue
        if v7_entry_logic(df, i, params):
            entry_price = df['Close'].iloc[i]
            atr = df['atr'].iloc[i] if 'atr' in df.columns else 1.0
            # Simulate exit: TP at +1.2%, SL at -0.8%, trailing after +0.5% (trail by 0.3%)
            tp_pct = 0.012
            sl_pct = 0.008
            trail_start = 0.005
            trail_pct = 0.003
            trail_active = False
            best_price = entry_price
            exit_price = None
            exit_type = None
            for j in range(i+1, min(i+max_bars, len(df))):
                current_price = df['Close'].iloc[j]
                profit = (current_price - entry_price) / entry_price
                if profit >= tp_pct:
                    exit_price = entry_price * (1 + tp_pct)
                    exit_type = 'take_profit'
                    break
                if (entry_price - current_price) / entry_price >= sl_pct:
                    exit_price = entry_price * (1 - sl_pct)
                    exit_type = 'stop_loss'
                    break
                if profit >= trail_start:
                    if not trail_active:
                        trail_active = True
                        best_price = current_price
                    else:
                        best_price = max(best_price, current_price)
                        trail_stop = best_price * (1 - trail_pct)
                        if current_price < trail_stop:
                            exit_price = trail_stop
                            exit_type = 'trailing_stop'
                            break
            if exit_price is None:
                j = min(i+max_bars-1, len(df)-1)
                exit_price = df['Close'].iloc[j]
                exit_type = 'max_bars_exit'
            open_until = j
            pnl = (exit_price - entry_price)
            equity += pnl
            trade_type = 'Long'  # v7 is long-only in this template
            trade_side = 'Buy'
            trades.append({
                "entry_idx": i,
                "exit_idx": j,
                "entry": entry_price,
                "exit": exit_price,
                "pnl": pnl,
                "equity": equity,
                "type": trade_type,
                "side": trade_side,
                "exit_type": exit_type,
            })
    return pd.DataFrame(trades)

# Usage example (replace with actual symbol and params):
# df = fetch_ohlcv('BTC/USD', timespan='YTD')
# params = get_v7_params(symbol='BTC/USD')
# trades = run_v7_backtest(df, params)
