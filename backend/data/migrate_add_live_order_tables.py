"""
Migration script: Add live order tracking tables to tradingcopilot.db.

This adds the missing live_order_trade_links and live_order_events tables
to support enhanced order tracking for live trading (matching paper trading capabilities).

Run this script to upgrade an existing database:
    python backend/data/migrate_add_live_order_tables.py [--db-path path/to/tradingcopilot.db]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"


def migrate(db_path: Path) -> int:
    """Add live order tracking tables if they don't exist."""
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path), timeout=30)
    c = conn.cursor()

    try:
        # Add live_order_trade_links table
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS live_order_trade_links (
                order_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                version TEXT NOT NULL,
                trade_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        print("✓ Created/verified live_order_trade_links table")

        # Add live_order_events table with enhanced columns for quantity/notional tracking
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS live_order_events (
                event_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                symbol TEXT,
                status TEXT,
                event_type TEXT,
                event_time TEXT,
                qty REAL,
                notional REAL,
                filled_qty REAL,
                submitted_at TEXT,
                raw_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        print("✓ Created/verified live_order_events table")

        # Also enhance paper_order_events if needed
        # Add missing columns to paper_order_events (won't fail if they exist)
        try:
            c.execute("ALTER TABLE paper_order_events ADD COLUMN qty REAL")
            print("✓ Added qty column to paper_order_events")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            c.execute("ALTER TABLE paper_order_events ADD COLUMN notional REAL")
            print("✓ Added notional column to paper_order_events")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            c.execute("ALTER TABLE paper_order_events ADD COLUMN filled_qty REAL")
            print("✓ Added filled_qty column to paper_order_events")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            c.execute("ALTER TABLE paper_order_events ADD COLUMN submitted_at TEXT")
            print("✓ Added submitted_at column to paper_order_events")
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.commit()
        print("\n✅ Migration complete!")
        return 0

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate tradingcopilot.db to add live order tracking tables."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help=f"Path to tradingcopilot.db (default: {DEFAULT_DB})",
    )

    args = parser.parse_args()
    return migrate(args.db_path)


if __name__ == "__main__":
    sys.exit(main())
