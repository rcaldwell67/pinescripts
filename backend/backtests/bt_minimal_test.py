import backtrader as bt
import pandas as pd

# Minimal test strategy: always buy on first bar
class TestStrategy(bt.Strategy):
    def next(self):
        if len(self) == 1 and not self.position:
            print("Submitting BUY order on first bar...")
            self.buy(size=0.00001)
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f"[ORDER] BUY EXECUTED, Price: {order.executed.price}, Size: {order.executed.size}")
            elif order.issell():
                print(f"[ORDER] SELL EXECUTED, Price: {order.executed.price}, Size: {order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"[ORDER] Order Canceled/Margin/Rejected")

    def next(self):
        print(f"Bar: {len(self)} | Position: {self.position.size if self.position else 0} | Cash: {self.broker.get_cash()} | Value: {self.broker.getvalue()}")
        if len(self) == 1 and not self.position:
            print("Submitting BUY order on first bar...")
            self.buy(size=0.00001)

# Load the same CSV as your main script
csv_path = "backend/data/btc_usd_5m_ytd.csv"
df = pd.read_csv(csv_path, parse_dates=True, index_col=0)
# Clean for Backtrader
cols_needed = ['open', 'high', 'low', 'close', 'volume']
df = df[[c for c in cols_needed if c in df.columns]]
df = df.apply(pd.to_numeric, errors='coerce')
df = df.dropna()
if df.index.tz is not None:
    df.index = df.index.tz_convert(None)
print("Data columns:", df.columns)
print("First row:\n", df.head(1))

# Backtrader expects columns: open, high, low, close, volume, datetime (index)
data = bt.feeds.PandasData(dataname=df)
cerebro = bt.Cerebro()
cerebro.addstrategy(TestStrategy)
cerebro.adddata(data)
cerebro.broker.setcash(10000)
cerebro.broker.setcommission(commission=0)
print("Starting Portfolio Value:", cerebro.broker.getvalue())
cerebro.run()
print("Final Portfolio Value:", cerebro.broker.getvalue())
