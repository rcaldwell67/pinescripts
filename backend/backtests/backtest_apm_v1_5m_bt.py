import os
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- Parameters (from original script) ---
EMA_FAST = 21; EMA_MID = 50; EMA_SLOW = 200
ADX_LEN = 14; RSI_LEN = 14; ATR_LEN = 14; VOL_LEN = 20
ATR_BL_LEN = 60
PB_PCT = 0.25
ADX_THRESH = 18
EMA_SLOPE_BARS = 3
MOMENTUM_BARS = 5
VOL_MULT = 0.3
MIN_BODY = 0.15
ATR_FLOOR = 0.001
PANIC_MULT = 1.5
RSI_LO_S = 30; RSI_HI_S = 58
SL_MULT = 4.0
TP_MULT = 6.0
TRAIL_ACT = 3.5
TRAIL_DIST = 0.1
MAX_BARS = 0
MACRO_EMA = 400
RISK_PCT = 0.035
INITIAL_CAPITAL = 10000.0
COMMISSION_PCT = 0.0006
TRADE_LONGS = False
TRADE_SHORTS = True
SESSION_START_ET = 9
SESSION_END_ET = 14

class APMv1Backtrader(bt.Strategy):
    params = dict(
        ema_fast=EMA_FAST,
        ema_mid=EMA_MID,
        ema_slow=EMA_SLOW,
        adx_len=ADX_LEN,
        rsi_len=RSI_LEN,
        atr_len=ATR_LEN,
        vol_len=VOL_LEN,
        atr_bl_len=ATR_BL_LEN,
        pb_pct=PB_PCT,
        adx_thresh=ADX_THRESH,
        ema_slope_bars=EMA_SLOPE_BARS,
        momentum_bars=MOMENTUM_BARS,
        vol_mult=0.0,
        min_body=MIN_BODY,
        atr_floor=ATR_FLOOR,
        panic_mult=PANIC_MULT,
        rsi_lo_s=RSI_LO_S,
        rsi_hi_s=RSI_HI_S,
        sl_mult=SL_MULT,
        tp_mult=TP_MULT,
        trail_act=TRAIL_ACT,
        trail_dist=TRAIL_DIST,
        max_bars=MAX_BARS,
        macro_ema=MACRO_EMA,
        risk_pct=RISK_PCT,
        commission_pct=COMMISSION_PCT,
        trade_longs=TRADE_LONGS,
        trade_shorts=TRADE_SHORTS,
        session_start=SESSION_START_ET,
        session_end=SESSION_END_ET,
        initial_capital=INITIAL_CAPITAL
    )

    def __init__(self):
        self.ema_fast = bt.ind.EMA(period=self.p.ema_fast)
        self.ema_mid = bt.ind.EMA(period=self.p.ema_mid)
        self.ema_slow = bt.ind.EMA(period=self.p.ema_slow)
        self.ema_macro = bt.ind.EMA(period=self.p.macro_ema) if self.p.macro_ema > 0 else None
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
        self.cooldown_bars = 0
        self.consec_losses = 0
        self.position_entry_price = None
        self.position_entry_time = None
        self.notional = 0

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f"[ORDER] BUY EXECUTED, Price: {order.executed.price}, Size: {order.executed.size}")
            elif order.issell():
                print(f"[ORDER] SELL EXECUTED, Price: {order.executed.price}, Size: {order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"[ORDER] Order Canceled/Margin/Rejected (ref {order.ref})")

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
        et_hour = self.data.datetime.datetime(0).hour
        # --- Indicator/Filter logic ---
        tol = self.p.pb_pct / 100.0
        is_trending = True  # Relaxed: always allow trending condition
        is_panic = False  # Relaxed: never block on panic condition
        atr_fl = self.atr[0] / close >= self.p.atr_floor
        # Relaxed: disable macro_bear filter for testing
        macro_bear = True  # (close < self.ema_macro[0]) if self.ema_macro is not None else True
        # Relaxed: disable ema_bear filter for testing
        ema_bear = True  # self.ema_fast[0] < self.ema_mid[0] and self.ema_mid[0] < self.ema_slow[0]
        # Relaxed: disable ema_slope_down filter for testing
        ema_slope_down = True  # self.ema_fast[0] < self.ema_fast[-self.p.ema_slope_bars] if self.p.ema_slope_bars > 0 else True
        # Relaxed: disable short_pb filter for testing
        short_pb = True  # self.data.high[-1] >= self.ema_fast[-1] * (1.0 - tol) and close < self.ema_fast[0] and close < open_
        # Relaxed: disable body_ok filter for testing
        body_ok = True  # abs(close - open_) / self.atr[0] >= self.p.min_body if self.atr[0] > 0 else False
        vol_ok = volume >= self.vol_ma[0] * self.p.vol_mult
        # Relaxed: disable rsi_falling filter for testing
        rsi_falling = True  # self.rsi[0] < self.rsi[-1]
        # Relaxed: disable rsi_short_ok filter for testing
        rsi_short_ok = True  # self.p.rsi_lo_s <= self.rsi[0] <= self.p.rsi_hi_s
        # Relaxed: disable mom_ok_s (momentum) filter for testing
        mom_ok_s = True  # close < self.datas[0].close[-self.p.momentum_bars]
        # Relaxed: disable session_ok filter for testing
        session_ok = True  # (et_hour >= self.p.session_start) and (et_hour < self.p.session_end)
        # --- Entry logic (shorts only) with debug ---
        short_checks = [
            (self.p.trade_shorts, f"trade_shorts: {self.p.trade_shorts}"),
            (short_pb, f"short_pb: {short_pb}"),
            (ema_bear, f"ema_bear: {ema_bear}"),
            (ema_slope_down, f"ema_slope_down: {ema_slope_down}"),
            (rsi_falling, f"rsi_falling: {rsi_falling}"),
            (rsi_short_ok, f"rsi_short_ok: {rsi_short_ok} (RSI={self.rsi[0]:.2f})"),
            (vol_ok, f"vol_ok: {vol_ok} (vol={volume:.2f}, vol_ma={self.vol_ma[0]:.2f})"),
            (body_ok, f"body_ok: {body_ok} (body={abs(close-open_):.4f}, ATR={self.atr[0]:.4f})"),
            (is_trending, f"is_trending: {is_trending} (ADX={self.adx[0]:.2f})"),
            (mom_ok_s, f"mom_ok_s: {mom_ok_s} (close={close:.2f}, close[-{self.p.momentum_bars}]={self.datas[0].close[-self.p.momentum_bars]:.2f})"),
            (session_ok, f"session_ok: {session_ok} (hour={et_hour})"),
            (not is_panic, f"not is_panic: {not is_panic} (ATR={self.atr[0]:.4f}, ATR_BL={self.atr_bl[0]:.4f})"),
            (atr_fl, f"atr_fl: {atr_fl} (ATR/close={self.atr[0]/close:.5f})"),
            (macro_bear, f"macro_bear: {macro_bear} (close={close:.2f}, ema_macro={self.ema_macro[0] if self.ema_macro is not None else 'N/A'})")
        ]
        short_cond = all(c[0] for c in short_checks)
        if not short_cond:
            print(f"[DEBUG] Short entry blocked on bar {len(self)}:")
            for passed, msg in short_checks:
                print(f"    {'OK' if passed else 'FAIL'} - {msg}")
        stop_dist = max(self.p.sl_mult * self.atr[0], 1e-6)
        risk_qty = equity * self.p.risk_pct / stop_dist if stop_dist > 0 else 0
        entry_qty = max(risk_qty, 0.001)
        if not pos and short_cond and self.cooldown_bars == 0:
            o = self.sell(size=entry_qty)
            self.sl = close + stop_dist
            self.tp = close - self.p.tp_mult * self.atr[0]
            self.best = close
            self.trail_active = False
            self.bar_in_trade = 0
            self.position_entry_price = close
            self.position_entry_time = self.data.datetime.datetime(0)
            self.notional = entry_qty * close
        # --- Exit logic ---
        if pos:
            self.best = min(self.best, low) if self.best is not None else low
            # Trail activation
            if not self.trail_active and (abs(pos.price - close) >= self.p.trail_act * self.atr[0]):
                self.trail_active = True
            # Trailing stop
            if self.trail_active:
                trail_sl = self.best + self.p.trail_dist * self.atr[0]
                self.sl = min(self.sl, trail_sl)
            # Hard SL/TP
            if high >= self.sl:
                self.close()
                self._record_trade('SL', close, equity)
            elif low <= self.tp:
                self.close()
                self._record_trade('TP', close, equity)
            # Max bars in trade
            if self.p.max_bars > 0 and self.bar_in_trade >= self.p.max_bars:
                self.close()
                self._record_trade('MB', close, equity)
        if self.cooldown_bars > 0:
            self.cooldown_bars -= 1

    def _record_trade(self, result, exit_price, equity):
        pnl_raw = (self.position_entry_price - exit_price) / self.position_entry_price
        dp = pnl_raw * self.notional - self.notional * self.p.commission_pct * 2
        self.trades.append({
            'entry_time': self.position_entry_time,
            'exit_time': self.data.datetime.datetime(0),
            'direction': 'short',
            'entry': self.position_entry_price,
            'exit': exit_price,
            'result': result,
            'pnl_pct': round(pnl_raw * 100, 3),
            'dollar_pnl': round(dp, 2),
            'equity': round(equity, 2)
        })
        if dp <= 0:
            self.consec_losses += 1
            if self.consec_losses >= 2:
                self.cooldown_bars = 1
                self.consec_losses = 0
        else:
            self.consec_losses = 0

if __name__ == "__main__":
    # Load data (assume yfinance or pre-saved CSV)
    csv_path = "backend/data/btc_usd_5m_ytd.csv"
    if not os.path.exists(csv_path):
        raise SystemExit(f"Data file not found: {csv_path}")
    df = pd.read_csv(csv_path, parse_dates=True, index_col=0)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df.index = pd.to_datetime(df.index)
    df = df[['open', 'high', 'low', 'close', 'volume']]
    df.dropna(inplace=True)
    data = bt.feeds.PandasData(dataname=df)
    cerebro = bt.Cerebro()
    cerebro.addstrategy(APMv1Backtrader)
    cerebro.adddata(data)
    cerebro.broker.setcash(INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=COMMISSION_PCT)
    results = cerebro.run()
    strat = results[0]
    trades = getattr(strat, 'trades', [])
    equity_curve = getattr(strat, 'equity_curve', [])
    total_trades = len(trades)
    wins = sum(1 for t in trades if t.get('dollar_pnl', 0) > 0)
    losses = total_trades - wins
    win_rate = (wins / total_trades * 100) if total_trades else 0
    start_val = INITIAL_CAPITAL
    end_val = equity_curve[-1] if equity_curve else cerebro.broker.getvalue()
    net_return = ((end_val - start_val) / start_val * 100) if start_val else 0
    eq_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(eq_arr)
    dd_arr = (eq_arr - peak) / peak * 100
    max_dd = dd_arr.min() if len(dd_arr) else 0
    print(f"\n--- Backtest Summary (APMv1Backtrader) ---")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Net Return: {net_return:.2f}%")
    print(f"Max Drawdown: {max_dd:.2f}%")
    print(f"Final Portfolio Value: {end_val:.2f}")
    # Print trade log
    if trades:
        print("\n--- Trade Log ---")
        for i, t in enumerate(trades, 1):
            print(f"{i:>3}  {t['entry_time']}  {t['exit_time']}  {t['direction']:>5}  {t['entry']:>7.4f}  {t['exit']:>7.4f}  {t['result']:>6}  {t['pnl_pct']:>+7.3f}%  {t['dollar_pnl']:>+8.2f}  {t['equity']:>9.2f}")
