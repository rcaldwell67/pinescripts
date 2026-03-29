
import os
from dotenv import load_dotenv
import backtrader as bt
import pandas as pd
import json
from datetime import datetime, timedelta
import argparse


# --- Adaptive Pullback Momentum v1.1 Strategy (Shorts Only) ---


class APMv1Strategy(bt.Strategy):
    params = dict(
        ema_fast=21,
        ema_mid=50,
        ema_slow=200,
        adx_thresh=28,
        adx_len=14,
        pb_pct=0.10,
        rsi_len=14,
        rsi_lo=42,
        rsi_hi=72,
        vol_len=20,
        vol_mult=1.0,
        min_body=0.30,
        atr_len=14,
        atr_bl_len=20,
        atr_floor=0.0,
        panic_mult=2.0,
        sl_mult=2.0,
        tp_mult=1.0,
        tr_act=2.0,
        tr_dist=0.4,
        risk_pct=0.01,
        max_bars=0,
        enable_shorts=True,
        enable_longs=True
    )

    def notify_order(self, order):
        print(f"[ORDER DEBUG] Order ref: {order.ref}, Status: {order.getstatusname()}, Size: {order.size}, Price: {order.created.price if order.created else 'N/A'}")
        if order.status in [order.Submitted, order.Accepted]:
            print(f"[ORDER DEBUG] Order Submitted/Accepted (ref {order.ref})")
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f"[ORDER] BUY EXECUTED, Price: {order.executed.price}, Size: {order.executed.size}")
            elif order.issell():
                print(f"[ORDER] SELL EXECUTED, Price: {order.executed.price}, Size: {order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"[ORDER] Order Canceled/Margin/Rejected (ref {order.ref})")

    def __init__(self):
        self.ema_fast = bt.ind.EMA(period=self.p.ema_fast)
        self.ema_mid = bt.ind.EMA(period=self.p.ema_mid)
        self.ema_slow = bt.ind.EMA(period=self.p.ema_slow)
        self.adx = bt.ind.ADX(period=self.p.adx_len)
        self.rsi = bt.ind.RSI(period=self.p.rsi_len)
        self.atr = bt.ind.ATR(period=self.p.atr_len)
        self.atr_bl = bt.ind.SMA(self.atr, period=self.p.atr_bl_len)
        self.vol_ma = bt.ind.SMA(self.data.volume, period=self.p.vol_len)
        self.trades = []
        self.equity_curve = []
        self.sl = None
        self.tp = None
        self.trail_active = False
        self.best = None
        self.bar_in_trade = 0
        # All trading logic moved to next()



if __name__ == "__main__":
    # Set CSV path and load/reformat DataFrame
    csv_path = "backend/data/btc_usd_5m_ytd.csv"
    if not os.path.exists(csv_path):
        print(f"[ERROR] Data file not found: {csv_path}\nRun fetch_alpaca_btcusd_5m_ytd.py first.")
        exit(1)
    df = pd.read_csv(csv_path, parse_dates=True, index_col=0)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df.index = pd.to_datetime(df.index)
    # Only keep required columns
    df = df[['open', 'high', 'low', 'close', 'volume']]
    df.dropna(inplace=True)
    if df.empty:
        print(f"[ERROR] No data in {csv_path} after reformat.")
        exit(1)
    # Print shape and sample of reformatted DataFrame
    print(f"[DEBUG] Reformatted DataFrame shape: {df.shape}")
    print("[DEBUG] Reformatted DataFrame sample:")
    print(df.head(10))
    parser = argparse.ArgumentParser(description="Backtest strategies")
    parser.add_argument("--symbol", type=str, default="BTC-USD", help="Symbol (use BTC-USD for yfinance)")
    parser.add_argument("--strategy", type=str, default="apm", choices=["apm", "APMv1Strategy"], help="Strategy")
    parser.add_argument("--cash", type=float, default=10000, help="Starting cash")
    args = parser.parse_args()

    data = bt.feeds.PandasData(dataname=df)
    cerebro = bt.Cerebro()
    # Select strategy based on CLI argument
    if args.strategy.lower() in ["apm", "apmv1strategy"]:
        cerebro.addstrategy(APMv1Strategy)
    else:
        raise ValueError(f"Unknown strategy: {args.strategy}")
    cerebro.adddata(data)
    cerebro.broker.setcash(args.cash)
    results = cerebro.run()
    strat = results[0]

    trades = getattr(strat, 'trades', [])
    equity_curve = getattr(strat, 'equity_curve', [])
    total_trades = len(trades)
    wins = sum(1 for t in trades if t.get('won'))
    losses = total_trades - wins
    win_rate = (wins / total_trades * 100) if total_trades else 0
    start_val = equity_curve[0] if equity_curve else args.cash
    end_val = equity_curve[-1] if equity_curve else cerebro.broker.getvalue()
    net_return = ((end_val - start_val) / start_val * 100) if start_val else 0
    peak = equity_curve[0] if equity_curve else start_val

    # Calculate max drawdown
    max_dd = 0
    peak_val = start_val
    for v in equity_curve:
        if v > peak_val:
            peak_val = v
        dd = (peak_val - v) / peak_val if peak_val else 0
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = max_dd * 100

    print("\n--- Backtest Summary (APMv1Strategy v6 guidelines) ---")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Net Return: {net_return:.2f}%")
    print(f"Max Drawdown: {max_dd_pct:.2f}%")
    print(f"Final Portfolio Value: {end_val:.2f}")

    def notify_trade(self, trade):
        if trade.isclosed:
            result = {
                'won': trade.pnl > 0,
                'pnl': trade.pnl,
                'size': trade.size,
                'price': trade.price,
                'barclose': self.datas[0].datetime.datetime(0)
            }
            self.trades.append(result)

    def next(self):
        pos = self.position
        close = self.datas[0].close[0]
        high = self.datas[0].high[0]
        low = self.datas[0].low[0]
        open_ = self.datas[0].open[0]
        volume = self.datas[0].volume[0]
        equity = self.broker.getvalue()
        self.equity_curve.append(equity)
        self.bar_in_trade = self.bar_in_trade + 1 if pos else 0

        # Debug output for indicators and position
        print(f"Bar: {len(self)} | Pos: {pos.size if pos else 0} | Close: {close:.2f} | EMA21: {self.ema_fast[0]:.2f} | EMA50: {self.ema_mid[0]:.2f} | EMA200: {self.ema_slow[0]:.2f} | ATR: {self.atr[0]:.4f}")

        # --- ENTRY LOGIC (v6) ---
        if not pos:
            # Long entry debug
            long_checks = [
                (close > self.ema_slow[0], f"close > EMA200: {close:.2f} > {self.ema_slow[0]:.2f}"),
                (self.ema_fast[0] > self.ema_mid[0], f"EMA21 > EMA50: {self.ema_fast[0]:.2f} > {self.ema_mid[0]:.2f}"),
                (self.data.low[-1] <= self.ema_fast[-1], f"prev-bar low <= EMA21: {self.data.low[-1]:.2f} <= {self.ema_fast[-1]:.2f}"),
                (close > self.ema_fast[0], f"close > EMA21: {close:.2f} > {self.ema_fast[0]:.2f}"),
                (self.p.rsi_lo <= self.rsi[0] <= self.p.rsi_hi, f"RSI in [{self.p.rsi_lo},{self.p.rsi_hi}]: {self.rsi[0]:.2f}"),
                (volume >= self.vol_ma[0] * self.p.vol_mult, f"volume >= VolSMA*mult: {volume:.6f} >= {self.vol_ma[0]*self.p.vol_mult:.6f}"),
                (self.adx[0] > self.p.adx_thresh, f"ADX > {self.p.adx_thresh}: {self.adx[0]:.2f}"),
                (abs(close - open_) >= self.p.min_body * self.atr[0], f"body >= min_body*ATR: {abs(close-open_):.6f} >= {(self.p.min_body*self.atr[0]):.6f}")
            ]
            long_cond = all(c[0] for c in long_checks)
            if not long_cond:
                print(f"[DEBUG] Long entry blocked on bar {len(self)}:")
                for passed, msg in long_checks:
                    print(f"    {'OK' if passed else 'FAIL'} - {msg}")

            # Short entry debug
            short_checks = [
                (close < self.ema_slow[0], f"close < EMA200: {close:.2f} < {self.ema_slow[0]:.2f}"),
                (self.ema_fast[0] < self.ema_mid[0], f"EMA21 < EMA50: {self.ema_fast[0]:.2f} < {self.ema_mid[0]:.2f}"),
                (self.data.high[-1] >= self.ema_fast[-1], f"prev-bar high >= EMA21: {self.data.high[-1]:.2f} >= {self.ema_fast[-1]:.2f}"),
                (close < self.ema_fast[0], f"close < EMA21: {close:.2f} < {self.ema_fast[0]:.2f}"),
                (self.p.rsi_lo <= self.rsi[0] <= self.p.rsi_hi, f"RSI in [{self.p.rsi_lo},{self.p.rsi_hi}]: {self.rsi[0]:.2f}"),
                (volume >= self.vol_ma[0] * self.p.vol_mult, f"volume >= VolSMA*mult: {volume:.6f} >= {self.vol_ma[0]*self.p.vol_mult:.6f}"),
                (self.adx[0] > self.p.adx_thresh, f"ADX > {self.p.adx_thresh}: {self.adx[0]:.2f}"),
                (abs(close - open_) >= self.p.min_body * self.atr[0], f"body >= min_body*ATR: {abs(close-open_):.6f} >= {(self.p.min_body*self.atr[0]):.6f}")
            ]
            short_cond = all(c[0] for c in short_checks)
            if not short_cond:
                print(f"[DEBUG] Short entry blocked on bar {len(self)}:")
                for passed, msg in short_checks:
                    print(f"    {'OK' if passed else 'FAIL'} - {msg}")

            stop_dist = max(self.p.sl_mult * self.atr[0], 1e-6)
            risk_qty = equity * self.p.risk_pct / stop_dist if stop_dist > 0 else 0
            entry_qty = max(risk_qty, 0.001)
            if long_cond and self.p.enable_longs:
                print(f"[DEBUG] Long entry signal on bar {len(self)} | Size: {entry_qty} | Price: {close}")
                o = self.buy(size=entry_qty)
                self.sl = close - stop_dist
                self.tp = close + self.p.tp_mult * self.atr[0]
                self.best = close
                self.trail_active = False
                self.bar_in_trade = 0
            elif short_cond and self.p.enable_shorts:
                print(f"[DEBUG] Short entry signal on bar {len(self)} | Size: {entry_qty} | Price: {close}")
                o = self.sell(size=entry_qty)
                self.sl = close + stop_dist
                self.tp = close - self.p.tp_mult * self.atr[0]
                self.best = close
                self.trail_active = False
                self.bar_in_trade = 0

        # --- EXIT LOGIC (v6) ---
        if pos:
            if pos.size > 0:
                self.best = max(self.best, high) if self.best is not None else high
            else:
                self.best = min(self.best, low) if self.best is not None else low
            # Trail activation
            if not self.trail_active and (abs(pos.price - close) >= self.p.tr_act * self.atr[0]):
                self.trail_active = True
            # Trailing stop
            if self.trail_active:
                if pos.size > 0:
                    trail_sl = self.best - self.p.tr_dist * self.atr[0]
                    self.sl = max(self.sl, trail_sl)
                else:
                    trail_sl = self.best + self.p.tr_dist * self.atr[0]
                    self.sl = min(self.sl, trail_sl)
            # Hard SL/TP
            if (pos.size > 0 and low <= self.sl) or (pos.size < 0 and high >= self.sl):
                print(f"[DEBUG] Stop loss hit on bar {len(self)}")
                self.close()
            elif (pos.size > 0 and high >= self.tp) or (pos.size < 0 and low <= self.tp):
                print(f"[DEBUG] Take profit hit on bar {len(self)}")
                self.close()
            # Max bars in trade
            if self.p.max_bars > 0 and self.bar_in_trade >= self.p.max_bars:
                print(f"[DEBUG] Max bars in trade exit on bar {len(self)}")
                self.close()

class SmaCrossoverStrategy(bt.Strategy):
        # ...existing code...
    params = dict(
        fast=10,
        slow=30,
        risk_pct=0.02,
        lev_cap=3.0,
        atr_period=14,
        atr_mult_sl=1.5,
        atr_mult_tp=3.0
    )


