
# Load only the project root .env before any other imports
import os
from dotenv import load_dotenv
root_env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
print(f"Explicitly loading: {root_env_path}")
loaded = load_dotenv(root_env_path, override=True)
print(f"load_dotenv returned: {loaded}")
print("Environment after loading .env:")
for k in sorted(os.environ):
    if k.startswith('APCA') or k.startswith('ALPACA'):
        print(f"{k}={os.environ[k]}")

# backtest_backtrader_alpaca.py
"""
Backtest Adaptive Pullback Momentum v4 (BTCUSD) using Backtrader and Alpaca historical data.
"""
import backtrader as bt
import pandas as pd
from alpaca_trade_api.rest import REST
from datetime import datetime, timedelta

# --- Strategy definition (placeholder, to be filled with v4 logic) ---
class AdaptivePullbackMomentumV4(bt.Strategy):
    def __init__(self):
        # Indicator parameters
        self.ema_fast = bt.ind.EMA(self.datas[0].close, period=21)
        self.ema_mid = bt.ind.EMA(self.datas[0].close, period=50)
        self.ema_slow = bt.ind.EMA(self.datas[0].close, period=200)
        self.rsi = bt.ind.RSI(self.datas[0].close, period=14)
        self.atr = bt.ind.ATR(self.datas[0], period=14)
        self.atr_bl = bt.ind.SMA(self.atr, period=60)
        self.vol_ma = bt.indicators.SimpleMovingAverage(self.datas[0].volume, period=20)
        self.adx = bt.ind.ADX(self.datas[0], period=14)
        # DI+ and DI- are available as adx.plusDI, adx.minusDI
        # Add more as needed for v4 logic
    def next(self):
        # Default v4 parameters
        # v4.2 Pine Script/legacy backtest defaults
        ADX_THRESH = 28
        PANIC_MULT = 1.3
        ATR_FLOOR = 0.0020
        PB_TOL = 0.0015  # 0.15% (legacy PB_PCT = 0.15)
        VOL_MULT = 1.5
        MIN_BODY = 0.25
        SLOPE_MIN_BARS = 3
        RSI_LO_L = 42; RSI_HI_L = 68
        RSI_LO_S = 32; RSI_HI_S = 58
        SL_MULT = 2.0
        TP_MULT = 3.5
        TRAIL_ACT = 2.5
        TRAIL_DIST = 1.5
        RISK_PCT = 0.03
        LEV_CAP = 5.0
        COMMISSION_PCT = 0.0006
        # Only trade if enough bars for indicators
        if len(self) < 200 + 60:
            return
        pos = self.position
        close = self.datas[0].close[0]
        open_ = self.datas[0].open[0]
        high = self.datas[0].high[0]
        low = self.datas[0].low[0]
        volume = self.datas[0].volume[0]
        ema_fast = self.ema_fast[0]
        ema_mid = self.ema_mid[0]
        ema_slow = self.ema_slow[0]
        rsi = self.rsi[0]
        atr = self.atr[0]
        atr_bl = self.atr_bl[0]
        vol_ma = self.vol_ma[0]
        adx = self.adx[0]
        # Previous bar
        prev_ema_fast = self.ema_fast[-1]
        prev_low = self.datas[0].low[-1]
        prev_high = self.datas[0].high[-1]
        prev_rsi = self.rsi[-1]
        prev_close = self.datas[0].close[-1]
        # Entry logic
        is_trending = adx > ADX_THRESH
        is_panic = atr > atr_bl * PANIC_MULT
        atr_floor_ok = atr / close >= ATR_FLOOR
        pb_tol_up = prev_ema_fast * (1.0 + PB_TOL)
        pb_tol_dn = prev_ema_fast * (1.0 - PB_TOL)
        body_size = abs(close - open_) / atr if atr else 0
        long_pb = prev_low <= pb_tol_up and close > ema_fast and close > open_ and body_size >= MIN_BODY
        short_pb = prev_high >= pb_tol_dn and close < ema_fast and close < open_ and body_size >= MIN_BODY
        ema_bull_full = ema_fast > ema_mid > ema_slow
        ema_bear_full = ema_fast < ema_mid < ema_slow
        ema_slope_up = ema_fast > self.ema_fast[-SLOPE_MIN_BARS]
        ema_slope_down = ema_fast < self.ema_fast[-SLOPE_MIN_BARS]
        rsi_rising = rsi > prev_rsi
        rsi_falling = rsi < prev_rsi
        vol_ok = volume >= vol_ma * VOL_MULT
        # Match legacy: add in_session filter (NY 9-12)
        dt = self.datas[0].datetime.datetime(0)
        et_hour = dt.astimezone().hour - (dt.astimezone().utcoffset().total_seconds() // 3600 - 5)  # crude NY offset
        in_session = 9 <= et_hour < 12
        long_ok = (not pos and not is_panic and is_trending and atr_floor_ok and in_session and long_pb and ema_bull_full and ema_slope_up and rsi_rising and RSI_LO_L <= rsi <= RSI_HI_L and vol_ok)
        short_ok = (not pos and not is_panic and is_trending and atr_floor_ok and in_session and short_pb and ema_bear_full and ema_slope_down and rsi_falling and RSI_LO_S <= rsi <= RSI_HI_S and vol_ok)
        # Position sizing
        stop_dist = atr * SL_MULT
        equity = self.broker.getvalue()
        risk_qty = equity * RISK_PCT / stop_dist if stop_dist > 0 else 0
        max_qty = equity * LEV_CAP / close if close > 0 else 0
        entry_qty = min(risk_qty, max_qty)
        # Entry
        if not pos:
            if long_ok and entry_qty > 0:
                self.buy(size=entry_qty)
                self.sl = close - atr * SL_MULT
                self.tp = close + atr * TP_MULT
                self.best = close
                self.trail_active = False
            elif short_ok and entry_qty > 0:
                self.sell(size=entry_qty)
                self.sl = close + atr * SL_MULT
                self.tp = close - atr * TP_MULT
                self.best = close
                self.trail_active = False
        else:
            # Manage trailing stop and exit
            if pos.size > 0:
                self.best = max(self.best, high)
                if not self.trail_active and self.best >= pos.price + atr * TRAIL_ACT:
                    self.trail_active = True
                if self.trail_active:
                    trail_sl = self.best - atr * TRAIL_DIST
                    self.sl = max(self.sl, trail_sl)
                if low <= self.sl:
                    self.close()
                elif high >= self.tp:
                    self.close()
            elif pos.size < 0:
                self.best = min(self.best, low)
                if not self.trail_active and self.best <= pos.price - atr * TRAIL_ACT:
                    self.trail_active = True
                if self.trail_active:
                    trail_sl = self.best + atr * TRAIL_DIST
                    self.sl = min(self.sl, trail_sl)
                if high >= self.sl:
                    self.close()
                elif low <= self.tp:
                    self.close()

# --- Fetch historical data from Alpaca ---
def fetch_alpaca_bars(symbol="BTCUSD", days=365):
    # Load .env from project root and .venv
    dotenv_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', '.env'),
        os.path.join(os.path.dirname(__file__), '..', '..', '.venv', '.env'),
    ]
    for path in dotenv_paths:
        if os.path.exists(path):
            load_dotenv(path, override=True)
    api_key = os.getenv('APCA_API_KEY_ID') or os.getenv('ALPACA_API_KEY')
    api_secret = os.getenv('APCA_API_SECRET_KEY') or os.getenv('ALPACA_API_SECRET')
    base_url = os.getenv('APCA_API_BASE_URL') or os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    print(f"APCA_API_KEY_ID: {api_key}")
    print(f"APCA_API_SECRET_KEY: {api_secret}")
    print(f"APCA_API_BASE_URL: {base_url}")
    api = REST(api_key, api_secret, base_url)
    end = datetime.utcnow().replace(microsecond=0)
    start = end - timedelta(days=days)
    # Format as RFC3339 (YYYY-MM-DDTHH:MM:SSZ)
    start_str = start.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end.strftime('%Y-%m-%dT%H:%M:%SZ')
    bars = api.get_crypto_bars("BTC/USD", '30Min', start=start_str, end=end_str).df
    # Only filter by exchange if the column exists
    if 'exchange' in bars.columns:
        bars = bars[bars['exchange'] == 'CBSE']  # Use Coinbase for BTCUSD
    bars.index = pd.to_datetime(bars.index)
    return bars

if __name__ == "__main__":
    df = fetch_alpaca_bars()
    data = bt.feeds.PandasData(dataname=df)
    cerebro = bt.Cerebro()
    cerebro.addstrategy(AdaptivePullbackMomentumV4)
    cerebro.adddata(data)
    cerebro.broker.setcash(10000.0)
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    strategies = cerebro.run()
    strat = strategies[0]
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
    # --- Metrics ---
    print(f"Strategy instance type: {type(strat)}")
    trades = getattr(strat, 'trades', [])
    equity_curve = getattr(strat, 'equity_curve', [])
    total_trades = len(trades)
    wins = sum(1 for t in trades if t['won'])
    losses = total_trades - wins
    win_rate = (wins / total_trades * 100) if total_trades else 0
    start_val = equity_curve[0] if equity_curve else 10000.0
    end_val = equity_curve[-1] if equity_curve else cerebro.broker.getvalue()
    net_return = ((end_val - start_val) / start_val * 100) if start_val else 0
    # Max drawdown
    peak = equity_curve[0] if equity_curve else start_val
    max_dd = 0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak else 0
        if dd > max_dd:
            max_dd = dd
    print(f'Trades: {total_trades} | Wins: {wins} | Losses: {losses}')
    print(f'Win rate: {win_rate:.2f}%')
    print(f'Net return: {net_return:.2f}%')
    print(f'Max drawdown: {max_dd*100:.2f}%')
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
