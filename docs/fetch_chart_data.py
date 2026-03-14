"""
fetch_chart_data.py — Generate static OHLCV JSON files for the APM dashboard.

Fetches a rolling 12-month window of bars from Alpaca and saves them to
docs/data/ as JSON for use by the GitHub Pages chart panel.

Run manually:
    cd /workspaces/pinescripts/docs
    python fetch_chart_data.py

Or automated via GitHub Actions (.github/workflows/refresh-chart-data.yml)
which runs this script on a schedule and commits the updated JSON.

Requirements:
    pip install alpaca-py python-dotenv
Environment (set in .env or GitHub Actions secrets):    ALPACA_MODE             paper | live  (default: paper)
    ALPACA_PAPER_API_KEY    paper trading key
    ALPACA_PAPER_API_SECRET paper trading secret
    ALPACA_LIVE_API_KEY     live  trading key
    ALPACA_LIVE_API_SECRET  live  trading secret

    Legacy fallback (used when _PAPER/_LIVE vars are absent):    ALPACA_API_KEY
    ALPACA_API_SECRET
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Load .env if present ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv optional — fall back to existing env vars

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

# ── Config ────────────────────────────────────────────────────────────────────
# Select credentials based on ALPACA_MODE (default: paper).
# Falls back to legacy ALPACA_API_KEY / ALPACA_API_SECRET if namespaced vars are absent.
_MODE = os.environ.get("ALPACA_MODE", "paper").strip().lower()
if _MODE == "live":
    API_KEY    = os.environ.get("ALPACA_LIVE_API_KEY")    or os.environ.get("ALPACA_API_KEY")
    API_SECRET = os.environ.get("ALPACA_LIVE_API_SECRET") or os.environ.get("ALPACA_API_SECRET")
else:
    API_KEY    = os.environ.get("ALPACA_PAPER_API_KEY")    or os.environ.get("ALPACA_API_KEY")
    API_SECRET = os.environ.get("ALPACA_PAPER_API_SECRET") or os.environ.get("ALPACA_API_SECRET")

OUT_DIR    = Path(__file__).parent / "data"

# Rolling window: now minus LOOKBACK_DAYS → current time (captures latest bars)
LOOKBACK_DAYS = 365
_now   = datetime.now(timezone.utc)
_end   = _now
_start = _end - timedelta(days=LOOKBACK_DAYS)

JOBS = {
    "CLM": {
        "tf":      TimeFrame(5, TimeFrameUnit.Minute),
        "start":   _start,
        "end":     _end,
        "outfile": "chart_clm.json",
    },
    "BTC/USD": {
        "symbol":  "BTC/USD",
        "tf":      TimeFrame(15, TimeFrameUnit.Minute),
        "start":   _start,
        "end":     _end,
        "outfile": "chart_btcusd.json",
        "crypto":  True,
    },
}


def fetch_stock(client, symbol, tf, start, end):
    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=tf,
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    bars = client.get_stock_bars(req)
    df = bars.df
    if df.empty:
        return []
    # Reset multi-index (symbol, timestamp) → flat
    df = df.reset_index()
    df = df[df["symbol"] == symbol].copy()
    df = df.sort_values("timestamp")
    return [
        {
            "t": int(row["timestamp"].timestamp()),
            "o": round(float(row["open"]),  6),
            "h": round(float(row["high"]),  6),
            "l": round(float(row["low"]),   6),
            "c": round(float(row["close"]), 6),
            "v": int(row["volume"]),
        }
        for _, row in df.iterrows()
    ]


def fetch_crypto(symbol, tf, start, end):
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    client = CryptoHistoricalDataClient()  # no auth needed
    req = CryptoBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=tf,
        start=start,
        end=end,
    )
    bars = client.get_crypto_bars(req)
    df = bars.df
    if df.empty:
        return []
    df = df.reset_index()
    df = df[df["symbol"] == symbol].copy()
    df = df.sort_values("timestamp")
    return [
        {
            "t": int(row["timestamp"].timestamp()),
            "o": round(float(row["open"]),  2),
            "h": round(float(row["high"]),  2),
            "l": round(float(row["low"]),   2),
            "c": round(float(row["close"]), 2),
            "v": round(float(row["volume"]), 4),
        }
        for _, row in df.iterrows()
    ]


def main():
    print(f"Mode: {_MODE.upper()}")
    if not API_KEY or not API_SECRET:
        sys.exit(
            f"ERROR: No Alpaca credentials found for mode '{_MODE}'.\n"
            f"Set ALPACA_{_MODE.upper()}_API_KEY / ALPACA_{_MODE.upper()}_API_SECRET "
            "(or legacy ALPACA_API_KEY / ALPACA_API_SECRET) in .env or GitHub Secrets."
        )

    stock_client = StockHistoricalDataClient(API_KEY, API_SECRET)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, cfg in JOBS.items():
        symbol = cfg.get("symbol", name)
        print(f"Fetching {name} {cfg['tf']} bars {cfg['start'].date()} → {cfg['end'].date()} …", end=" ", flush=True)
        if cfg.get("crypto"):
            bars = fetch_crypto(symbol, cfg["tf"], cfg["start"], cfg["end"])
        else:
            bars = fetch_stock(stock_client, symbol, cfg["tf"], cfg["start"], cfg["end"])
        out = OUT_DIR / cfg["outfile"]
        with open(out, "w") as f:
            json.dump({
                "symbol": name,
                "timeframe": str(cfg["tf"]),
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bars": bars,
            }, f, separators=(",", ":"))
        kb = out.stat().st_size / 1024
        print(f"{len(bars):,} bars → {out.name} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
