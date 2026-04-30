import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_API_SECRET = os.getenv('ALPACA_API_SECRET')

trading_client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=True)

def place_market_order(symbol, qty, side):
    order_data = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL,
        time_in_force=TimeInForce.DAY
    )
    order = trading_client.submit_order(order_data)
    return order

def get_positions():
    return trading_client.get_all_positions()

def get_orders():
    return trading_client.get_orders()
