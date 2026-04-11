"""Enable/disable live trading for a symbol in tradingcopilot.db."""

import os
import sqlite3
import sys


DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../docs/data/tradingcopilot.db")
)


def _parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if v in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value!r}")


def set_symbol_live_enabled(symbol: str, live_enabled: bool) -> int:
    import shutil
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "ALTER TABLE symbols ADD COLUMN live_enabled INTEGER NOT NULL DEFAULT 1"
        )
    except sqlite3.OperationalError:
        # Column already exists.
        pass

    cur = conn.execute(
        "UPDATE symbols SET live_enabled = ? WHERE UPPER(symbol) = UPPER(?)",
        (1 if live_enabled else 0, symbol),
    )
    conn.commit()
    conn.close()
    # Copy to frontend-react/public/data
    public_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend-react/public/data/tradingcopilot.db'))
    try:
        shutil.copyfile(DB_PATH, public_db_path)
        print(f"Copied DB to {public_db_path}")
    except Exception as e:
        print(f"Warning: Failed to copy DB to frontend-react/public/data: {e}")
    return cur.rowcount


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
