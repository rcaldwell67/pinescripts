import os
from dotenv import load_dotenv
import backtrader as bt
import pandas as pd
import json
from datetime import datetime, timedelta

# --- SMA Crossover Strategy ---
class SmaCrossoverStrategy(bt.Strategy):
    params = dict(
        fast=10,
        slow=30,
        risk_pct=0.02,
        lev_cap=3.0
    )

    def __init__(self):
        self.sma_fast = bt.ind.SMA(period=self.p.fast)
        self.sma_slow = bt.ind.SMA(period=self.p.slow)
        self.crossover = bt.ind.CrossOver(self.sma_fast, self.sma_slow)
        self.trades = []
        self.equity_curve = []
        self.sl = None
        self.tp = None
        self.best = None
        self.trail_active = False

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
        equity = self.broker.getvalue()
        self.equity_curve.append(equity)
        stop_dist = (self.sma_slow[0] * 0.01)  # 1% stop
        risk_qty = equity * self.p.risk_pct / stop_dist if stop_dist > 0 else 0
        max_qty = equity * self.p.lev_cap / close if close > 0 else 0
        entry_qty = min(risk_qty, max_qty)

        # Entry
        if not pos:
            if self.crossover > 0 and entry_qty > 0:
                self.buy(size=entry_qty)
                self.sl = close - stop_dist
                self.tp = close + stop_dist * 2
                self.best = close
                self.trail_active = False
            elif self.crossover < 0 and entry_qty > 0:
                self.sell(size=entry_qty)
                self.sl = close + stop_dist
                self.tp = close - stop_dist * 2
                self.best = close
                self.trail_active = False
        else:
            # Manage trailing stop and exit
            if pos.size > 0:
                self.best = max(self.best, high)
                if not self.trail_active and self.best >= pos.price + stop_dist:
                    self.trail_active = True
                if self.trail_active:
                    trail_sl = self.best - stop_dist * 0.5
                    self.sl = max(self.sl, trail_sl)
                if low <= self.sl:
                    self.close()
                elif high >= self.tp:
                    self.close()
            elif pos.size < 0:
                self.best = min(self.best, low)
                if not self.trail_active and self.best <= pos.price - stop_dist:
                    self.trail_active = True
                if self.trail_active:
                    trail_sl = self.best + stop_dist * 0.5
                    self.sl = min(self.sl, trail_sl)
                if high >= self.sl:
                    self.close()
                elif low <= self.tp:
                    self.close()

def fetch_yfinance_bars(symbol="BTCUSD", interval="5m", period="60d"):
    import yfinance as yf
    yf_symbol = symbol.replace("USD", "-USD") if symbol.endswith("USD") else symbol
    print(f"Fetching {yf_symbol} {interval} {period} from yfinance…")
    raw = yf.download(yf_symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if raw.empty:
        raise RuntimeError(f"No data returned for {yf_symbol} {interval} {period}.")
    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()
    df.index = pd.to_datetime(df.index)
    print(f"  Rows: {len(df)}  |  {df.index[0].date()} → {df.index[-1].date()}")
    return df

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backtest strategies for a given symbol and version.")
    parser.add_argument('--symbol', type=str, default='BTCUSD', help='Symbol to backtest (e.g. BTCUSD, CLM, etc)')
    parser.add_argument('--strategy', type=str, default='sma', choices=['sma'], help='Strategy to use: sma')
    args = parser.parse_args()
    symbol = args.symbol
    strategy_choice = args.strategy

    if strategy_choice == 'sma':
        print(f"\n--- Backtest for {symbol} (SMA Crossover) ---\n")
        interval = "5m"
        df = fetch_yfinance_bars(symbol=symbol, interval=interval, period="60d")
        data = bt.feeds.PandasData(dataname=df)
        cerebro = bt.Cerebro()
        cerebro.addstrategy(SmaCrossoverStrategy)
        cerebro.adddata(data)
        cerebro.broker.setcash(10000.0)
        print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
        strategies = cerebro.run()
        strat = strategies[0]
        print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
        trades = getattr(strat, 'trades', [])
        equity_curve = getattr(strat, 'equity_curve', [])
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.get('won'))
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades else 0
        start_val = equity_curve[0] if equity_curve else 10000.0
        end_val = equity_curve[-1] if equity_curve else cerebro.broker.getvalue()
        net_return = ((end_val - start_val) / start_val * 100) if start_val else 0
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


