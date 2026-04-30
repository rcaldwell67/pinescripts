import os
import mariadb
import pandas as pd
from dotenv import load_dotenv

def write_results_to_db(results_csv, table_name="strategy_results_v7"):
    """Write results from a CSV file to the specified MariaDB table."""
    # Load environment variables from .env in project root or .venv/.env
    env_path = os.path.join(os.path.dirname(__file__), '../../.env')
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(__file__), '../../.venv/.env')
    load_dotenv(env_path)
    DB_CONFIG = {
        "user": os.environ.get("MARIADB_USER", "root"),
        "password": os.environ.get("MARIADB_PASSWORD", ""),
        "host": os.environ.get("MARIADB_HOST", "localhost"),
        "port": int(os.environ.get("MARIADB_PORT", 3306)),
        "database": os.environ.get("MARIADB_DATABASE", "tradingcopilot"),
    }
    df = pd.read_csv(results_csv)
    if df.empty:
        print(f"No results to write from {results_csv}.")
        return
    conn = mariadb.connect(**DB_CONFIG)
    cur = conn.cursor()
    cols = list(df.columns)
    placeholders = ','.join(['%s'] * len(cols))
    insert_sql = f"INSERT INTO {table_name} ({','.join(cols)}) VALUES ({placeholders})"
    for row in df.itertuples(index=False, name=None):
        cur.execute(insert_sql, row)
    conn.commit()
    cur.close()
    conn.close()
    print(f"Wrote {len(df)} rows from {results_csv} to {table_name}.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Write results CSV to MariaDB table.")
    parser.add_argument("--csv", type=str, required=True, help="CSV file with results")
    parser.add_argument("--table", type=str, default="strategy_results_v7", help="Target MariaDB table")
    args = parser.parse_args()
    write_results_to_db(args.csv, args.table)
