"""Enable/disable live trading for a symbol in tradingcopilot.db."""


import os
import sys
import mysql.connector
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))



def get_db_conn():
    return mysql.connector.connect(
        host=os.environ.get("MARIADB_HOST", "localhost"),
        user=os.environ.get("MARIADB_USER", "root"),
        password=os.environ.get("MARIADB_PASSWORD", ""),
        database=os.environ.get("MARIADB_DATABASE", "tradingcopilot"),
        port=int(os.environ.get("MARIADB_PORT", 3306)),
    )


def _parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if v in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value!r}")



def set_symbol_live_enabled(symbol: str, live_enabled: bool) -> int:
    conn = get_db_conn()
    cur = conn.cursor()
    # MariaDB: Use %s for parameters, and IFNULL for default
    cur.execute(
        "UPDATE symbols SET live_enabled = %s WHERE UPPER(symbol) = UPPER(%s)",
        (1 if live_enabled else 0, symbol),
    )
    conn.commit()
    rowcount = cur.rowcount
    conn.close()
    return rowcount


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python backend/data/set_symbol_live_enabled.py SYMBOL ENABLED")
        print("Example: python backend/data/set_symbol_live_enabled.py CLM false")
        return 1

    symbol = str(sys.argv[1]).strip()
    if not symbol:
        print("Symbol is required", file=sys.stderr)
        return 1

    try:
        enabled = _parse_bool(sys.argv[2])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    updated = set_symbol_live_enabled(symbol, enabled)
    if updated == 0:
        print(f"Symbol not found: {symbol}", file=sys.stderr)
        return 2

    print(f"Updated {symbol}: live_enabled={1 if enabled else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
