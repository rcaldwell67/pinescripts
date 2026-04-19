
import os
import dotenv
import mysql.connector
import json
from datetime import datetime, timezone
from pathlib import Path
import argparse

# Load .env if present
dotenv.load_dotenv(dotenv.find_dotenv())

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUTS = [
    REPO_ROOT / "frontend-react" / "public" / "data" / "dashboard_snapshot.json",
]

def get_db_conn():
    return mysql.connector.connect(
        host=os.environ.get("MARIADB_HOST", "localhost"),
        user=os.environ.get("MARIADB_USER", "root"),
        password=os.environ.get("MARIADB_PASSWORD", ""),
        database=os.environ.get("MARIADB_DATABASE", "tradingcopilot"),
        port=int(os.environ.get("MARIADB_PORT", 3306)),
    )

def fetch_symbols(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM symbols ORDER BY symbol")
    rows = cur.fetchall()
    # Convert any datetime objects to ISO strings for JSON serialization
    for row in rows:
        for k, v in row.items():
            if hasattr(v, 'isoformat'):
                row[k] = v.isoformat()
    return rows

def build_snapshot(trade_limit=200):
    conn = get_db_conn()
    try:
        symbols = fetch_symbols(conn)
        # Fetch backtest results
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT symbol, version, metrics FROM backtest_results")
        rows = cur.fetchall()
        backtest_results = []
        for row in rows:
            symbol = row["symbol"]
            version = row["version"].lower() if row["version"] else "v6"
            symbol_key = ''.join(ch for ch in symbol.upper() if ch.isalnum())
            try:
                metrics = json.loads(row["metrics"] or "{}")
            except Exception:
                metrics = {}
            # Flatten for dashboard: add symbol, version, symbol_key
            result_obj = {
                "symbol": symbol,
                "version": version,
                "symbol_key": symbol_key,
            }
            result_obj.update(metrics)
            backtest_results.append(result_obj)
        results = {"backtest": backtest_results}
        snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "account": {},
            "symbols": symbols,
            "results": results,
            "trades": [],
        }
        return snapshot
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", type=int, default=200)
    parser.add_argument("--out", action="append", dest="outs", default=[])
    args = parser.parse_args()
    output_paths = [Path(p) for p in args.outs] if args.outs else DEFAULT_OUTPUTS
    snapshot = build_snapshot(trade_limit=args.trades)
    for out_path in output_paths:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
