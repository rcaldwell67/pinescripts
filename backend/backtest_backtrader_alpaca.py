"""
CLI entry point for running a backtest on a symbol+version pair.
Fetches YTD 5-minute OHLCV data from Alpaca, runs the strategy,
and writes a summary row to docs/data/tradingcopilot.db.

Usage:
    python backend/backtest_backtrader_alpaca.py --symbol "BTC/USD" --version v1
    python backend/backtest_backtrader_alpaca.py --symbol "BTC/USD" --version v6

Requires env vars (or a .env file):
    ALPACA_API_KEY / ALPACA_PAPER_API_KEY
    ALPACA_API_SECRET / ALPACA_PAPER_API_SECRET
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Bootstrap path so strategy_generator imports work ─────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
SG_DIR    = REPO_ROOT / "backend" / "strategy_generator"
sys.path.insert(0, str(SG_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY")    or os.getenv("ALPACA_PAPER_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_PAPER_API_SECRET")

DB_PATH = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"

VERSION_MAP: dict[str, str] = {
    "v1": "APM v1.0-5m",
    "v2": "APM v2.0-10m",
    "v3": "APM v3.0",
    "v4": "APM v4.0",
    "v5": "APM v5.0",
    "v6": "APM v6.0",
}


# ── Data fetch ─────────────────────────────────────────────────────────────────

def fetch_ohlcv_alpaca(symbol: str) -> "pd.DataFrame | None":
    """Fetch from Alpaca. Returns None if subscription/access denied."""
    import pandas as pd
    from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit  # type: ignore[attr-defined]
    from alpaca.common.exceptions import APIError

    now   = datetime.now(tz=timezone.utc)
    start = datetime(now.year, 1, 1, tzinfo=timezone.utc)   # YTD
    tf = TimeFrame(5, TimeFrameUnit.Minute)

    is_crypto = "/" in symbol
    try:
        if is_crypto:
            client = CryptoHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
            req    = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start, end=now)
            df     = client.get_crypto_bars(req).df
        else:
            client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
            req    = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start, end=now)
            df     = client.get_stock_bars(req).df
    except APIError as e:
        # 403 = subscription/access denied (e.g., no market data subscription for stocks)
        if "403" in str(e) or "subscription" in str(e).lower():
            print(f"  Alpaca API access denied (subscription required): {e}", file=sys.stderr)
            return None
        raise

    if df.empty:
        raise RuntimeError(f"No data returned from Alpaca for {symbol}")

    df = df.reset_index()
    # Multi-symbol DataFrames have a 'symbol' column; keep our symbol only
    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol]

    # Normalise timestamp column
    ts_col = next((c for c in ("timestamp", "time") if c in df.columns), df.columns[0])
    df = df.rename(columns={ts_col: "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Rename to Title-case for strategy modules that expect Close/High/Low/Open/Volume
    col_map = {c: c.capitalize() for c in ("open", "high", "low", "close", "volume")}
    df = df.rename(columns=col_map)
    return df


def fetch_ohlcv_yfinance(symbol: str) -> "pd.DataFrame":
    """Fetch from Yahoo Finance as fallback (1h bars instead of 5m)."""
    import pandas as pd
    import yfinance as yf

    now = datetime.now(tz=timezone.utc)
    start = datetime(now.year, 1, 1, tzinfo=timezone.utc)

    # Download 1h data (yfinance doesn't support 5m without a subscription)
    print(f"  Fetching from Yahoo Finance (1h bars)...", file=sys.stderr)
    df = yf.download(symbol, start=start, end=now, interval="1h", progress=False)

    if df.empty:
        raise RuntimeError(f"No data returned from Yahoo Finance for {symbol}")

    # Reset index to convert Date from index to column
    df = df.reset_index()

    # Normalize column names. In some yfinance versions, columns may be tuples
    # (MultiIndex), e.g. ('Open', 'CLM'). Flatten before lowercasing.
    def _norm_col_name(col: object) -> str:
        if isinstance(col, tuple):
            parts = [str(p).strip() for p in col if p not in (None, "")]
            return (parts[0] if parts else str(col)).lower()
        return str(col).strip().lower()

    df.columns = [_norm_col_name(c) for c in df.columns]

    # Accept common timestamp column variants from different providers/versions
    ts_col = next((c for c in ("date", "datetime", "timestamp", "index") if c in df.columns), None)
    if ts_col is None:
        raise RuntimeError(f"Yahoo Finance data missing timestamp column. Columns: {list(df.columns)}")
    df = df.rename(columns={ts_col: "timestamp"})
    
    # Ensure required columns exist
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        raise RuntimeError(f"Yahoo Finance data missing columns: {required - set(df.columns)}")
    
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Capitalize column names for strategy compatibility
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    
    # Select only required columns
    df = df[["timestamp", "Open", "High", "Low", "Close", "Volume"]]
    
    print(f"  {len(df):,} hourly bars fetched from Yahoo Finance", file=sys.stderr)
    return df


def fetch_ohlcv(symbol: str) -> "pd.DataFrame":
    """Fetch OHLCV data, trying Alpaca first, then Yahoo Finance as fallback."""
    # Try Alpaca first
    df = fetch_ohlcv_alpaca(symbol)
    if df is not None:
        return df
    
    # Fall back to Yahoo Finance
    print(f"  Falling back to Yahoo Finance for {symbol}...", file=sys.stderr)
    return fetch_ohlcv_yfinance(symbol)


# ── Run strategy ───────────────────────────────────────────────────────────────

def run_backtest(
    df: "pd.DataFrame",
    version: str,
    symbol: str | None = None,
    profile: str | None = None,
) -> "pd.DataFrame":
    if version == "v1":
        from apm_v1_backtest import backtest_apm_v1
        from v1_params import get_v1_params

        return backtest_apm_v1(df, params=get_v1_params(symbol=symbol, profile=profile))
    if version == "v2":
        from apm_v2_backtest import backtest_apm_v2
        from v2_params import get_v2_params

        return backtest_apm_v2(df, params=get_v2_params(symbol=symbol, profile=profile))
    if version == "v3":
        from apm_v2_backtest import backtest_apm_v2
        from v3_params import get_v3_params

        return backtest_apm_v2(df, params=get_v3_params(symbol=symbol, profile=profile))
    if version == "v4":
        from apm_v2_backtest import backtest_apm_v2
        from v4_params import get_v4_params

        return backtest_apm_v2(df, params=get_v4_params(symbol=symbol, profile=profile))
    if version == "v5":
        from apm_v2_backtest import backtest_apm_v2
        from v5_params import get_v5_params

        return backtest_apm_v2(df, params=get_v5_params(symbol=symbol, profile=profile))
    if version == "v6":
        from apm_v2_backtest import backtest_apm_v2
        from v6_params import get_v6_params

        return backtest_apm_v2(df, params=get_v6_params(symbol=symbol, profile=profile))
    raise ValueError(f"Unknown version: {version!r}. Valid values: {list(VERSION_MAP)}")


# ── Persist results ────────────────────────────────────────────────────────────

def _to_native(val):
    if hasattr(val, "item"):
        return val.item()
    if hasattr(val, "to_pydatetime"):
        return str(val)
    return val


def _timestamp_at(df, idx):
    try:
        i = int(idx)
    except (TypeError, ValueError):
        return None
    if i < 0 or i >= len(df):
        return None
    if "timestamp" not in df.columns:
        return None
    try:
        return str(df["timestamp"].iloc[i])
    except Exception:
        return None


def _result_label(exit_type):
    raw = str(exit_type or "").strip().upper()
    if raw in {"TP", "TAKE_PROFIT"}:
        return "TP"
    if raw in {"SL", "STOP", "STOP_LOSS"}:
        return "SL"
    if "TRAIL" in raw:
        return "TRAIL"
    if raw in {"MB", "MAX_BARS", "MAX_BARS_IN_TRADE"}:
        return "MB"
    return raw or None


def save_to_db(symbol: str, version: str,
               trades: "pd.DataFrame", df: "pd.DataFrame") -> None:
    if trades.empty:
        print("No trades generated — skipping DB write.")
        return

    pnl_col    = "pnl"       if "pnl"       in trades.columns else "dollar_pnl"
    equity_col = "equity"    if "equity"     in trades.columns else "equity"

    initial_equity = trades[equity_col].iloc[0] - trades[pnl_col].iloc[0]
    final_equity   = trades[equity_col].iloc[-1]
    total_trades   = len(trades)
    win_trades     = int((trades[pnl_col] > 0).sum())
    loss_trades    = int((trades[pnl_col] <= 0).sum())
    win_rate       = win_trades / total_trades * 100 if total_trades else 0
    avg_pnl        = float(trades[pnl_col].mean())
    total_pnl      = float(trades[pnl_col].sum())
    max_drawdown   = float((trades[equity_col].cummax() - trades[equity_col]).max())
    net_return_pct = (final_equity - initial_equity) / initial_equity * 100 if initial_equity else 0

    # Map entry_idx → timestamp if available
    first_trade_date = last_trade_date = None
    if "entry_idx" in trades.columns and "timestamp" in df.columns:
        try:
            first_trade_date = str(df["timestamp"].iloc[int(trades["entry_idx"].iloc[0])])
            last_trade_date  = str(df["timestamp"].iloc[int(trades["entry_idx"].iloc[-1])])
        except Exception:
            pass

    metrics = {
        "version":          version,
        "beginning_equity": _to_native(initial_equity),
        "final_equity":     _to_native(final_equity),
        "total_trades":     _to_native(total_trades),
        "winning_trades":   _to_native(win_trades),
        "losing_trades":    _to_native(loss_trades),
        "win_rate":         _to_native(win_rate),
        "average_pnl":      _to_native(avg_pnl),
        "total_pnl":        _to_native(total_pnl),
        "max_drawdown":     _to_native(max_drawdown),
        "net_return_pct":   _to_native(net_return_pct),
        "first_trade_date": first_trade_date,
        "last_trade_date":  last_trade_date,
    }

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=DELETE")
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass

    # Replace the existing summary row for this symbol+version (if any)
    notes = f"{VERSION_MAP.get(version, version)} backtest summary"
    conn.execute(
        "DELETE FROM backtest_results WHERE symbol = ? AND notes LIKE ?",
        (symbol, f"%{VERSION_MAP.get(version, version)}%"),
    )
    conn.execute(
        "INSERT INTO backtest_results (symbol, metrics, notes) VALUES (?, ?, ?)",
        (symbol, json.dumps(metrics), notes),
    )

    norm_symbol = "".join(ch for ch in symbol.upper() if ch.isalnum())
    conn.execute(
        """
        DELETE FROM trades
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND LOWER(version) = ?
          AND mode = 'backtest'
        """,
        (norm_symbol, version),
    )

    trade_rows = []
    for _, trade in trades.iterrows():
        entry_time = _timestamp_at(df, trade.get("entry_idx"))
        exit_time = _timestamp_at(df, trade.get("exit_idx"))
        entry_price = float(trade.get("entry", trade.get("entry_price", 0.0)) or 0.0)
        exit_price = float(trade.get("exit", trade.get("exit_price", 0.0)) or 0.0)
        dollar_pnl = float(trade.get("pnl", trade.get("dollar_pnl", 0.0)) or 0.0)
        equity = float(trade.get("equity", 0.0) or 0.0)
        beginning_equity = equity - dollar_pnl
        pnl_pct = (dollar_pnl / beginning_equity * 100.0) if beginning_equity else None

        side = str(trade.get("side", trade.get("direction", "")) or "").lower().strip()
        direction = side if side in ("long", "short") else "short"

        trade_rows.append(
            (
                symbol,
                version,
                "backtest",
                entry_time,
                exit_time,
                direction,
                entry_price,
                exit_price,
                _result_label(trade.get("exit_type", trade.get("result"))),
                pnl_pct,
                dollar_pnl,
                equity,
                "simulation",
            )
        )

    if trade_rows:
        conn.executemany(
            """
            INSERT INTO trades (
                symbol, version, mode, entry_time, exit_time, direction,
                entry_price, exit_price, result, pnl_pct, dollar_pnl, equity, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            trade_rows,
        )

    conn.commit()
    conn.close()
    print(f"Results saved to DB: {symbol} {version}  "
          f"trades={total_trades}  net={net_return_pct:.1f}%")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Run an APM backtest and save results to the DB.")
    parser.add_argument("--symbol",  required=True, help="Trading symbol, e.g. BTC/USD")
    parser.add_argument("--version", required=True, help="Strategy version (v1-v6)")
    parser.add_argument("--profile", help="Optional runtime profile override, e.g. eth_focus")
    args = parser.parse_args()

    symbol  = args.symbol.strip()
    version = args.version.strip().lower()

    if version not in VERSION_MAP:
        print(f"ERROR: version {version!r} is not implemented. Valid: {list(VERSION_MAP)}",
              file=sys.stderr)
        return 1

    print(f"Fetching YTD OHLCV for {symbol}...")
    try:
        df = fetch_ohlcv(symbol)
    except Exception as e:
        print(f"ERROR: Failed to fetch data for {symbol}: {e}", file=sys.stderr)
        return 1
    
    print(f"  {len(df):,} bars fetched ({df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]})")

    profile = args.profile.strip() if args.profile else None

    if profile:
        print(f"Running backtest {version} (profile={profile})...")
    else:
        print(f"Running backtest {version}...")

    trades = run_backtest(df, version, symbol=symbol, profile=profile)
    print(f"  {len(trades)} trades generated")

    save_to_db(symbol, version, trades, df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
