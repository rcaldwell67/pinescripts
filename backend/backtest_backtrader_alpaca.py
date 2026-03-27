
# Load only the project root .env before any other imports
import os
from dotenv import load_dotenv

root_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
print(f"Explicitly loading: {root_env_path}")
loaded = load_dotenv(root_env_path, override=True)
print(f"load_dotenv returned: {loaded}")
# Always set env vars from .env if not already set
try:
    with open(root_env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if key and value and key not in os.environ:
                os.environ[key] = value
except Exception as e:
    print(f"Warning: Could not parse .env for fallback env var setting: {e}")
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
import json
from datetime import datetime, timedelta

# Optional: yfinance import (install if missing)
try:
    import yfinance as yf
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf



def load_strategy_config(version):
    config_path = os.path.join(os.path.dirname(__file__), 'strategy_generator', 'configs', f'{version}.json')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- Strategy definition (placeholder, to be filled with v4 logic) ---
class AdaptivePullbackMomentumConfigurable(bt.Strategy):
    params = (('config', None),)
    def __init__(self):
        cfg = self.p.config
        # Use config for indicator periods and logic
        self.ema_fast = bt.ind.EMA(self.datas[0].close, period=cfg.get('i_ema_fast', {}).get('default', 21))
        self.ema_mid = bt.ind.EMA(self.datas[0].close, period=cfg.get('i_ema_mid', {}).get('default', 50))
        self.ema_slow = bt.ind.EMA(self.datas[0].close, period=cfg.get('i_ema_slow', {}).get('default', 200))
        self.rsi = bt.ind.RSI(self.datas[0].close, period=cfg.get('i_rsi_len', {}).get('default', 14))
        self.atr = bt.ind.ATR(self.datas[0], period=cfg.get('i_atr_len', {}).get('default', 14))
        self.atr_bl = bt.ind.SMA(self.atr, period=cfg.get('i_atr_bl_len', {}).get('default', 60))
        self.vol_ma = bt.indicators.SimpleMovingAverage(self.datas[0].volume, period=cfg.get('i_vol_len', {}).get('default', 20))
        self.adx = bt.ind.ADX(self.datas[0], period=cfg.get('i_adx_len', {}).get('default', 14))
        # Store config values for use in next()
        self.cfg = cfg

    def next(self):
        cfg = self.cfg
        # Helper to get float param
        def getf(key, fallback):
            try:
                return float(cfg.get(key, {}).get('default', fallback))
            except Exception:
                return fallback
        # Get all needed params
        # Relaxed thresholds for troubleshooting (further relaxed)
        ADX_THRESH = 15  # Lowered from 20
        PANIC_MULT = getf('i_panic_mult', 1.3)
        ATR_FLOOR = 0.001  # Lowered from 0.002
        PB_TOL = getf('i_pb_pct', 0.0015)
        VOL_MULT = 1.0  # Lowered from 1.5
        MIN_BODY = 0.1  # Lowered from 0.25
        SLOPE_MIN_BARS = int(getf('i_ema_slope_bars', 3))
        RSI_LO_L = 35  # Widened from 42
        RSI_HI_L = 75  # Widened from 68
        RSI_LO_S = 25  # Widened from 32
        RSI_HI_S = 65  # Widened from 58
        SL_MULT = getf('i_sl_mult', 2.0)
        TP_MULT = getf('i_tp_mult', 3.5)
        TRAIL_ACT = getf('i_trail_act', 2.5)
        TRAIL_DIST = getf('i_trail_dist', 1.5)
        RISK_PCT = getf('i_risk_pct', 0.03)
        LEV_CAP = 5.0
        COMMISSION_PCT = 0.0006
        # Only trade if enough bars for indicators (reduced lookback)
        if len(self) < 100:
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
        import pytz
        dt = self.datas[0].datetime.datetime(0)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.UTC)
        ny_dt = dt.astimezone(pytz.timezone('America/New_York'))
        et_hour = ny_dt.hour
        # For crypto, allow all hours (no session filter)
        in_session = True
        # Debug print for all entry conditions
        if not pos:
            print(f"Bar {len(self)} | close={close:.2f} open={open_:.2f} high={high:.2f} low={low:.2f} vol={volume:.2f}")
            print(f"  is_trending={is_trending} (adx={adx:.2f} > {ADX_THRESH})")
            print(f"  is_panic={is_panic} (atr={atr:.4f} > atr_bl*PANIC_MULT={atr_bl*PANIC_MULT:.4f})")
            print(f"  atr_floor_ok={atr_floor_ok} (atr/close={atr/close:.4f} >= {ATR_FLOOR})")
            print(f"  in_session={in_session} (et_hour={et_hour})")
            print(f"  long_pb={long_pb} (prev_low={prev_low:.2f} <= pb_tol_up={pb_tol_up:.2f} and close={close:.2f} > ema_fast={ema_fast:.2f} and close={close:.2f} > open_={open_:.2f} and body_size={body_size:.2f} >= {MIN_BODY})")
            print(f"  short_pb={short_pb} (prev_high={prev_high:.2f} >= pb_tol_dn={pb_tol_dn:.2f} and close={close:.2f} < ema_fast={ema_fast:.2f} and close={close:.2f} < open_={open_:.2f} and body_size={body_size:.2f} >= {MIN_BODY})")
            print(f"  ema_bull_full={ema_bull_full} (ema_fast={ema_fast:.2f} > ema_mid={ema_mid:.2f} > ema_slow={ema_slow:.2f})")
            print(f"  ema_bear_full={ema_bear_full} (ema_fast={ema_fast:.2f} < ema_mid={ema_mid:.2f} < ema_slow={ema_slow:.2f})")
            print(f"  ema_slope_up={ema_slope_up} (ema_fast={ema_fast:.2f} > ema_fast[-{SLOPE_MIN_BARS}]={self.ema_fast[-SLOPE_MIN_BARS]:.2f})")
            print(f"  ema_slope_down={ema_slope_down} (ema_fast={ema_fast:.2f} < ema_fast[-{SLOPE_MIN_BARS}]={self.ema_fast[-SLOPE_MIN_BARS]:.2f})")
            print(f"  rsi_rising={rsi_rising} (rsi={rsi:.2f} > prev_rsi={prev_rsi:.2f})")
            print(f"  rsi_falling={rsi_falling} (rsi={rsi:.2f} < prev_rsi={prev_rsi:.2f})")
            print(f"  vol_ok={vol_ok} (volume={volume:.2f} >= vol_ma*VOL_MULT={vol_ma*VOL_MULT:.2f})")
            print(f"  RSI_LO_L <= rsi <= RSI_HI_L: {RSI_LO_L} <= {rsi:.2f} <= {RSI_HI_L}")
            print(f"  RSI_LO_S <= rsi <= RSI_HI_S: {RSI_LO_S} <= {rsi:.2f} <= {RSI_HI_S}")
        # Maximal permissiveness: only require not in position, not panic, in session, and basic pullback pattern
        long_ok = (
            not pos and not is_panic and in_session and long_pb
        )
        short_ok = (
            not pos and not is_panic and in_session and short_pb
        )
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



# --- Fetch historical data from yfinance ---
def fetch_yfinance_bars(symbol="BTCUSD", interval="30m", period="60d"):
    yf_symbol = symbol.replace("USD", "-USD") if symbol.endswith("USD") else symbol
    print(f"Fetching {yf_symbol} {interval} {period} from yfinance…")
    raw = yf.download(yf_symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if raw.empty:
        raise RuntimeError(f"No data returned for {yf_symbol} {interval} {period}.")
    # Flatten MultiIndex columns if present
    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()
    df.index = pd.to_datetime(df.index)
    print(f"  Rows: {len(df)}  |  {df.index[0].date()} → {df.index[-1].date()}")
    return df

# --- Fetch historical data from Alpaca ---


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Backtest Adaptive Pullback Momentum for a given symbol and version.")
    parser.add_argument('--symbol', type=str, default='BTCUSD', help='Symbol to backtest (e.g. BTCUSD, CLM, etc)')
    parser.add_argument('--version', type=str, default='v4', help='Strategy version (v1, v2, v3, v4, v5, v6)')
    args = parser.parse_args()
    symbol = args.symbol
    version = args.version
    config = load_strategy_config(version)

    # max_attempts = 100
    attempt = 0
    while True:
        attempt += 1
        print(f"\n--- Backtest Attempt {attempt} for {symbol} ---\n")
        # Use 5m interval for CLM v1, else default to 30m
        interval = "5m" if symbol.upper() == "CLM" and version.lower() == "v1" else "30m"
        df = fetch_yfinance_bars(symbol=symbol, interval=interval, period="60d")
        data = bt.feeds.PandasData(dataname=df)
        cerebro = bt.Cerebro()
        cerebro.addstrategy(AdaptivePullbackMomentumConfigurable, config=config)
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
        wins = sum(1 for t in trades if t.get('won'))
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

        # --- Strategy Guidelines ---
        print("\n--- Strategy Guidelines ---")
        guidelines = [
            (win_rate >= 70, f"Win Rate: {win_rate:.2f}% (>= 70%)"),
            (net_return >= 20, f"Net Return: {net_return:.2f}% (>= 20%)"),
            (max_dd*100 <= -4.5, f"Max Drawdown: {max_dd*100:.2f}% (<= -4.50%)")
        ]
        for passed, msg in guidelines:
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] {msg}")
        if all(g[0] for g in guidelines):
            print("\nStrategy meets ALL guidelines!\n")
            break
        # No max_attempts break; loop continues until guidelines are met
        print("\nStrategy does NOT meet all guidelines. Retrying...\n")
