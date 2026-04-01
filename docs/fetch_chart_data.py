"""
Fetch 5-minute OHLCV bars for all dashboard symbols from Alpaca and store
them in docs/data/tradingcopilot.db (chart_data + chart_meta tables).

Symbols:
  Crypto: BTC/USD  ETH/USD
  Stocks: CLM  CRF

Run locally:
  pip install alpaca-py python-dotenv pytz
  python docs/fetch_chart_data.py

In GitHub Actions the ALPACA_API_KEY / ALPACA_API_SECRET env vars are
injected via repository secrets (see .github/workflows/refresh-chart-data.yml).
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Optional: load .env when running locally
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Resolve API credentials — prefer live keys, fall back to paper keys
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY")    or os.getenv("ALPACA_PAPER_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_PAPER_API_SECRET")

DB_PATH      = Path(__file__).parent / "data" / "tradingcopilot.db"
LOOKBACK_DAYS = 200   # Calendar days of history to include

# ── Symbols ──────────────────────────────────────────────────────────────────

CRYPTO_SYMBOLS: list[str] = ["BTC/USD", "ETH/USD"]
STOCK_SYMBOLS:  list[str] = ["CLM", "CRF"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_bar(row, ts_col: str) -> tuple:
    """Return (t_unix, o, h, l, c, v) tuple."""
    t = row[ts_col]
    if hasattr(t, "timestamp"):
        t_unix = int(t.timestamp())
    else:
        t_unix = int(datetime.fromisoformat(str(t)).replace(tzinfo=timezone.utc).timestamp())
    return (
        t_unix,
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        float(row.get("volume", 0)),
    )


def _detect_ts_col(df) -> str:
    for name in ("timestamp", "time"):
        if name in df.columns:
            return name
    return df.columns[0]


# ── Fetch functions ───────────────────────────────────────────────────────────

def fetch_crypto(symbol: str, start: datetime, end: datetime) -> list[tuple]:
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit  # type: ignore[attr-defined]

    client = CryptoHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
    req = CryptoBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=start,
        end=end,
    )
    df = client.get_crypto_bars(req).df
    if df.empty:
        return []

    df = df.reset_index()
    ts_col = _detect_ts_col(df)
    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol]
    df = df.sort_values(ts_col)
    return [_row_to_bar(row, ts_col) for _, row in df.iterrows()]


def fetch_stock(symbol: str, start: datetime, end: datetime) -> list[tuple]:
    import pandas as pd
    import yfinance as yf
    from alpaca.common.exceptions import APIError
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit  # type: ignore[attr-defined]

    client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
    try:
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )
        df = client.get_stock_bars(req).df
        if not df.empty:
            df = df.reset_index()
            ts_col = _detect_ts_col(df)
            if "symbol" in df.columns:
                df = df[df["symbol"] == symbol]
            df = df.sort_values(ts_col)
            return [_row_to_bar(row, ts_col) for _, row in df.iterrows()]
    except APIError as exc:
        print(f"  Alpaca stock fetch fallback for {symbol}: {exc}", file=sys.stderr)

    # Fallback for symbols/feed combinations not available from Alpaca.
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end, interval="1h", auto_adjust=False)
    if df.empty:
        return []

    df = df.reset_index()
    ts_col = next((c for c in ("Datetime", "Date", "datetime", "date") if c in df.columns), None)
    if ts_col is None:
        ts_col = df.columns[0]
    df = df.rename(columns={ts_col: "timestamp", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp")
    return [_row_to_bar(row, "timestamp") for _, row in df.iterrows()]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chart_data (
            symbol TEXT    NOT NULL,
            t      INTEGER NOT NULL,
            o      REAL    NOT NULL,
            h      REAL    NOT NULL,
            l      REAL    NOT NULL,
            c      REAL    NOT NULL,
            v      REAL    NOT NULL,
            PRIMARY KEY (symbol, t)
        );
        CREATE TABLE IF NOT EXISTS chart_meta (
            symbol       TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL
        );
    """)


def save_to_db(conn: sqlite3.Connection, symbol: str,
               bars: list[tuple], generated_at: datetime) -> None:
    """Replace all bars for *symbol* and update its metadata row."""
    conn.execute("DELETE FROM chart_data WHERE symbol = ?", (symbol,))
    conn.executemany(
        "INSERT INTO chart_data (symbol, t, o, h, l, c, v) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(symbol, *bar) for bar in bars],
    )
    conn.execute(
        "INSERT OR REPLACE INTO chart_meta (symbol, generated_at) VALUES (?, ?)",
        (symbol, generated_at.isoformat()),
    )
    conn.commit()
    print(f"  Saved {len(bars):,} bars for {symbol}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    now   = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=LOOKBACK_DAYS)
    end   = now
    errors = 0

    print(f"Fetching chart data  start={start.date()}  end={end.date()}\n")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # Use DELETE journal mode so no -wal/-shm files are left behind after close
    conn.execute("PRAGMA journal_mode=DELETE")
    _ensure_tables(conn)

    for symbol in CRYPTO_SYMBOLS:
        print(f"[crypto] {symbol}")
        try:
            bars = fetch_crypto(symbol, start, end)
            save_to_db(conn, symbol, bars, now)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            errors += 1

    for symbol in STOCK_SYMBOLS:
        print(f"[stock]  {symbol}")
        try:
            bars = fetch_stock(symbol, start, end)
            save_to_db(conn, symbol, bars, now)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            errors += 1

    conn.close()
    print(f"\nDone. {errors} error(s).")
    return errors


if __name__ == "__main__":
    sys.exit(main())

