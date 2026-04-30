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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
