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
def prepare_v7_signal_frame(df, params):
    # Calculate all indicators used in v1–v6
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
    # Add more features as needed from v1–v6
    return df

# --- Example entry/exit logic (to be customized per symbol) ---
def v7_entry_logic(df, i, params):
    # Example: combine v1–v6 filters, add new v7 logic here
    # This is a placeholder; customize for your symbol
    signal = params["signal"]
    # Trend, momentum, volatility, and multi-factor confirmation
    trend_ok = df['ema_fast'].iloc[i] > df['ema_mid'].iloc[i] > df['ema_slow'].iloc[i]
    rsi_ok = 40 < df['rsi'].iloc[i] < 70
    macd_ok = df['macd_line'].iloc[i] > df['macd_signal_line'].iloc[i]
    stoch_ok = df['stoch_k'].iloc[i] > 20 and df['stoch_d'].iloc[i] > 20
    cci_ok = -100 < df['cci'].iloc[i] < 100
    # Require at least 3/5 factors
    factors = [trend_ok, rsi_ok, macd_ok, stoch_ok, cci_ok]
    return sum(factors) >= 3

# --- Main v7 backtest loop (all timespans) ---
def run_v7_backtest(df, params):
    df = prepare_v7_signal_frame(df, params)
    entries = []
    equity = 100000.0
    for i in range(max(200, int(params['signal']['ema_slow'])), len(df)):
        if v7_entry_logic(df, i, params):
            # Use the date or index for time tracking
            if 'Date' in df.columns:
                trade_date = df['Date'].iloc[i]
            elif 'date' in df.columns:
                trade_date = df['date'].iloc[i]
            else:
                trade_date = df.index[i] if hasattr(df.index, '__getitem__') else i
            pnl = np.random.normal(10, 50)  # placeholder PnL
            equity += pnl
            entries.append({
                "entry_idx": i,
                "date": trade_date,
                "pnl": pnl,
                "equity": equity,
            })
    # Return as DataFrame for compatibility with runner
    return pd.DataFrame(entries)

# Usage example (replace with actual symbol and params):
# df = fetch_ohlcv('BTC/USD', timespan='YTD')
# params = get_v7_params(symbol='BTC/USD')
# trades = run_v7_backtest(df, params)
