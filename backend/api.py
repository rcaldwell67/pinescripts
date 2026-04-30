# --- Live Trading Endpoint ---
from live_trading import place_market_order, get_positions, get_orders

# POST /api/live-trade
@app.route('/api/live-trade', methods=['POST'])
def live_trade():
    data = request.get_json()
    symbol = data.get('symbol')
    qty = data.get('qty')
    side = data.get('side')
    if not symbol or not qty or not side:
        return jsonify({'error': 'symbol, qty, and side are required'}), 400
    try:
        order = place_market_order(symbol, qty, side)
        return jsonify({'order': order.model_dump() if hasattr(order, 'model_dump') else str(order)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# GET /api/live-positions
@app.route('/api/live-positions', methods=['GET'])
def live_positions():
    try:
        positions = get_positions()
        return jsonify({'positions': [p.model_dump() if hasattr(p, 'model_dump') else str(p) for p in positions]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# GET /api/live-orders
@app.route('/api/live-orders', methods=['GET'])
def live_orders():
    try:
        orders = get_orders()
        return jsonify({'orders': [o.model_dump() if hasattr(o, 'model_dump') else str(o) for o in orders]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
from strategy_engine import evaluate_strategy
import pandas as pd

# POST /api/strategy/evaluate
@app.route('/api/strategy/evaluate', methods=['POST'])
def strategy_evaluate():
    data = request.get_json()
    trades = pd.DataFrame(data.get('trades', []))
    result = evaluate_strategy(trades)
    return jsonify(result)


# POST /api/backtest (runs backtest and returns metrics)
@app.route('/api/backtest', methods=['POST'])
def backtest():
    from backtest_backtrader_alpaca import fetch_ohlcv, run_backtest
    data = request.get_json()
    symbol = data.get('symbol')
    version = data.get('version', 'v1')
    timespan = data.get('timespan', 'YTD')
    profile = data.get('profile')
    params = data.get('params')
    if not symbol or not version:
        return jsonify({'error': 'symbol and version are required'}), 400
    try:
        df = fetch_ohlcv(symbol, timespan=timespan)
        trades = run_backtest(df, version, symbol=symbol, profile=profile, params=params)
        from strategy_engine import evaluate_strategy
        metrics = evaluate_strategy(trades)
        return jsonify({
            'symbol': symbol,
            'version': version,
            'timespan': timespan,
            'metrics': metrics,
            'trades': trades.to_dict(orient='records')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request
import mysql.connector

load_dotenv()

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('MARIADB_HOST', 'localhost'),
        user=os.getenv('MARIADB_USER', 'root'),
        password=os.getenv('MARIADB_PASSWORD', ''),
        database=os.getenv('MARIADB_DATABASE', 'tradingcopilot'),
        port=int(os.getenv('MARIADB_PORT', 3306))
    )

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

# Example: Get all active symbols
def fetch_active_symbols():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM symbols WHERE isactive = 1')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

@app.route('/api/symbols', methods=['GET'])
def get_symbols():
    try:
        rows = fetch_active_symbols()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- New: Data Ingestion and News Sentiment Endpoints ---
from data_ingestion import fetch_yfinance_bars
from news_sentiment import fetch_news_headlines, analyze_sentiment

@app.route('/api/yfinance-bars', methods=['GET'])
def get_yfinance_bars():
    symbol = request.args.get('symbol')
    start = request.args.get('start')
    end = request.args.get('end')
    interval = request.args.get('interval', '1d')
    if not symbol or not start or not end:
        return jsonify({'error': 'symbol, start, and end are required'}), 400
    try:
        df = fetch_yfinance_bars(symbol, start, end, interval)
        return df.reset_index().to_json(orient='records')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/news-sentiment', methods=['GET'])
def get_news_sentiment():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({'error': 'symbol is required'}), 400
    try:
        headlines = fetch_news_headlines(symbol)
        avg_sentiment = analyze_sentiment(headlines)
        return jsonify({'symbol': symbol, 'avg_sentiment': avg_sentiment, 'headlines': headlines})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
