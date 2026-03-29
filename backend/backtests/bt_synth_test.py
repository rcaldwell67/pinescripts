import backtrader as bt
import pandas as pd
from datetime import datetime, timedelta

# Create a simple synthetic DataFrame
start = datetime(2026, 1, 1)
dates = [start + timedelta(days=i) for i in range(10)]
data = {
    'open': [100 + i for i in range(10)],
    'high': [101 + i for i in range(10)],
    'low': [99 + i for i in range(10)],
    'close': [100.5 + i for i in range(10)],
    'volume': [1000 for _ in range(10)]
}
df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))

class TestStrategy(bt.Strategy):
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
            self.buy(size=1)

feed = bt.feeds.PandasData(dataname=df)
cerebro = bt.Cerebro()
cerebro.addstrategy(TestStrategy)
cerebro.adddata(feed)
cerebro.broker.setcash(10000)
cerebro.broker.setcommission(commission=0)
print("Starting Portfolio Value:", cerebro.broker.getvalue())
cerebro.run()
print("Final Portfolio Value:", cerebro.broker.getvalue())
