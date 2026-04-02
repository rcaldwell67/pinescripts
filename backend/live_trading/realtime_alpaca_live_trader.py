"""
Real-time Alpaca LIVE Trading runner for APM versions.

Safety model:
- This script will not place live orders unless ALLOW_ALPACA_LIVE_TRADING=true.
- It uses Alpaca live endpoint by default (https://api.alpaca.markets).

Usage:
    python backend/live_trading/realtime_alpaca_live_trader.py --all-symbols --version v1
    python backend/live_trading/realtime_alpaca_live_trader.py --symbol CLM --version v1
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from apm_v1 import apm_v1_latest_bar_analysis
from apm_v2 import apm_v2_latest_bar_analysis
from apm_v3 import apm_v3_latest_bar_analysis
from apm_v4 import apm_v4_latest_bar_analysis
from apm_v5 import apm_v5_latest_bar_analysis
from apm_v6 import apm_v6_latest_bar_analysis
from backtest_backtrader_alpaca import DB_PATH, VERSION_MAP, fetch_ohlcv
from portfolio_system import evaluate_trade
from v1_params import get_v1_params
from v2_params import get_v2_params
from v3_params import get_v3_params
from v4_params import get_v4_params
from v5_params import get_v5_params
from v6_params import get_v6_params

ALPACA_LIVE_BASE = os.getenv("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets")
STRATEGY_PARAMS: dict[str, dict[str, Any]] = {
    "v1": get_v1_params(),
    "v2": get_v2_params(),
    "v3": get_v3_params(),
    "v4": get_v4_params(),
    "v5": get_v5_params(),
    "v6": get_v6_params(),
}


def _strategy_params(version: str) -> dict[str, Any]:
    return STRATEGY_PARAMS.get(version, STRATEGY_PARAMS["v1"])


def _entry_analysis(df, side: str, version: str) -> dict[str, Any]:
    params = _strategy_params(version)
    if version == "v2":
        return apm_v2_latest_bar_analysis(df, side=side, params=params)
    if version == "v3":
        return apm_v3_latest_bar_analysis(df, side=side, params=params)
    if version == "v4":
        return apm_v4_latest_bar_analysis(df, side=side, params=params)
    if version == "v5":
        return apm_v5_latest_bar_analysis(df, side=side, params=params)
    if version == "v6":
        return apm_v6_latest_bar_analysis(df, side=side, params=params)
    return apm_v1_latest_bar_analysis(df, side=side, params=params)


class AlpacaLiveAPI:
    def __init__(self) -> None:
        key = os.getenv("ALPACA_LIVE_API_KEY") or os.getenv("ALPACA_API_KEY")
        secret = os.getenv("ALPACA_LIVE_API_SECRET") or os.getenv("ALPACA_API_SECRET")
        if not key or not secret:
            raise RuntimeError(
                "Missing Alpaca live credentials. Set ALPACA_LIVE_API_KEY/ALPACA_LIVE_API_SECRET "
                "or ALPACA_API_KEY/ALPACA_API_SECRET."
            )

        self.headers = {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
        url = f"{ALPACA_LIVE_BASE}{path}"
        resp = requests.request(method, url, headers=self.headers, params=params, json=payload, timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Alpaca LIVE {method} {path} failed: {resp.status_code} {resp.text}")
        if not resp.text:
            return None
        return resp.json()

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def get_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        params = {"status": "open", "symbols": symbol, "direction": "desc", "limit": 50}
        data = self._request("GET", "/v2/orders", params=params)
        return data if isinstance(data, list) else []

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/v2/positions/{symbol}")
        except RuntimeError as exc:
            if "404" in str(exc):
                return None
            raise

    def submit_short_bracket(self, *, symbol: str, qty: float, take_profit: float, stop_loss: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "side": "sell",
            "type": "market",
            "time_in_force": "day",
            "qty": str(max(qty, 0.0)),
            "order_class": "bracket",
            "take_profit": {"limit_price": f"{take_profit:.6f}"},
            "stop_loss": {"stop_price": f"{stop_loss:.6f}"},
        }
        return self._request("POST", "/v2/orders", payload=payload)

    def submit_long_bracket(self, *, symbol: str, qty: float, take_profit: float, stop_loss: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "qty": str(max(qty, 0.0)),
            "order_class": "bracket",
            "take_profit": {"limit_price": f"{take_profit:.6f}"},
            "stop_loss": {"stop_price": f"{stop_loss:.6f}"},
        }
        return self._request("POST", "/v2/orders", payload=payload)

    def get_fill_activities(self, *, after: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"direction": "asc", "page_size": 100}
        if after:
            params["after"] = after
        data = self._request("GET", "/v2/account/activities/FILL", params=params)
        return data if isinstance(data, list) else []


def _order_symbol(symbol: str) -> str:
    return symbol.replace("/", "")


def _load_symbols_from_db() -> list[str]:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    rows = conn.execute("SELECT symbol FROM symbols ORDER BY symbol").fetchall()
    conn.close()
    return [row[0] for row in rows]


def _latest_signal_is_entry(df, side: str = "short", version: str = "v1") -> bool:
    return bool(_entry_analysis(df, side=side, version=version).get("is_entry"))


def _can_short_symbol(symbol: str) -> bool:
    """Return True if the broker supports shorting this symbol on the live account."""
    # Alpaca live does not support short-selling of crypto spot pairs.
    return "/" not in symbol


def _compute_order_params(
    df,
    account_equity: float,
    side: str = "short",
    version: str = "v1",
    risk_multiplier: float = 1.0,
) -> tuple[float, float, float] | None:
    risk = _strategy_params(version)["risk"]
    if len(df) < 210:
        return None
    if "atr" not in df.columns:
        return None

    price = float(df["Close"].iloc[-1])
    atr = float(df["atr"].iloc[-1])
    if atr <= 0:
        return None

    if side == "long":
        sl = price - float(risk["sl_atr_mult"]) * atr
        tp = price + float(risk["tp_atr_mult"]) * atr
        risk_per_unit = price - sl
    else:
        sl = price + float(risk["sl_atr_mult"]) * atr
        tp = price - float(risk["tp_atr_mult"]) * atr
        risk_per_unit = sl - price

    if risk_per_unit <= 0:
        return None

    risk_budget = max(account_equity * float(risk["risk_pct"]) / 100.0 * max(risk_multiplier, 0.0), 1.0)
    qty = round(risk_budget / risk_per_unit, 6)
    if qty <= 0:
        return None

    return qty, tp, sl


def _upsert_summary(conn: sqlite3.Connection, symbol: str, version: str, status: str, detail: str, equity: float | None) -> None:
    notes = f"{VERSION_MAP.get(version, version)} realtime alpaca live summary"
    metrics = {
        "symbol": symbol,
        "version": version,
        "status": status,
        "detail": detail,
        "equity": equity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(
        "DELETE FROM live_trading_results WHERE symbol = ? AND notes LIKE ?",
        (symbol, f"%{VERSION_MAP.get(version, version)} realtime alpaca live%"),
    )
    conn.execute(
        "INSERT INTO live_trading_results (symbol, metrics, notes) VALUES (?, ?, ?)",
        (symbol, json.dumps(metrics), notes),
    )


def _ensure_fill_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS live_fill_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id TEXT UNIQUE NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            qty REAL,
            price REAL,
            transaction_time TEXT,
            order_id TEXT,
            raw_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
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
    conn.execute(
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


def _fill_exists(conn: sqlite3.Connection, activity_id: str) -> bool:
    """Check if a fill event already exists in the database."""
    row = conn.execute("SELECT 1 FROM live_fill_events WHERE activity_id = ? LIMIT 1", (activity_id,)).fetchone()
    return bool(row)


def _link_order_to_trade(conn: sqlite3.Connection, order_id: str, symbol: str, version: str, trade_id: int, role: str) -> None:
    """Link an order to a trade (entry or exit role)."""
    if not order_id:
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO live_order_trade_links (order_id, symbol, version, trade_id, role)
        VALUES (?, ?, ?, ?, ?)
        """,
        (order_id, symbol, version, trade_id, role),
    )


def _trade_for_order(conn: sqlite3.Connection, order_id: str) -> tuple[int, str] | None:
    """Retrieve the trade linked to an order."""
    if not order_id:
        return None
    row = conn.execute(
        "SELECT trade_id, role FROM live_order_trade_links WHERE order_id = ? LIMIT 1",
        (order_id,),
    ).fetchone()
    if not row:
        return None
    return int(row[0]), str(row[1])


def _sync_fill_events(conn: sqlite3.Connection, api: AlpacaLiveAPI, symbols: list[str], version: str) -> int:
    _ensure_fill_table(conn)
    row = conn.execute("SELECT MAX(transaction_time) FROM live_fill_events").fetchone()
    after = row[0] if row and row[0] else None

    db_symbol_by_order_symbol = {_order_symbol(s): s for s in symbols}
    fills = api.get_fill_activities(after=after)
    inserted = 0

    for fill in fills:
        act_id = str(fill.get("id") or "").strip()
        order_symbol = str(fill.get("symbol") or "").strip()
        db_symbol = db_symbol_by_order_symbol.get(order_symbol, order_symbol)
        side = str(fill.get("side") or "").lower().strip()
        qty = float(fill.get("qty") or 0.0)
        price = float(fill.get("price") or 0.0)
        ts = str(fill.get("transaction_time") or "")
        order_id = str(fill.get("order_id") or "")

        if not act_id or not db_symbol:
            continue

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO live_fill_events (
                activity_id, symbol, side, qty, price, transaction_time, order_id, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (act_id, db_symbol, side, qty, price, ts, order_id, json.dumps(fill)),
        )
        if cur.rowcount != 1:
            continue
        inserted += 1

        if side == "sell":
            conn.execute(
                """
                INSERT INTO trades (
                    symbol, version, mode, entry_time, exit_time, direction,
                    entry_price, exit_price, result, pnl_pct, dollar_pnl, equity
                ) VALUES (?, ?, 'live', ?, NULL, 'short', ?, NULL, 'OPEN', NULL, NULL, NULL)
                """,
                (db_symbol, version, ts, price),
            )
        elif side == "buy":
            open_row = conn.execute(
                """
                SELECT id, entry_price
                FROM trades
                WHERE symbol = ? AND version = ? AND mode = 'live' AND direction = 'short' AND exit_time IS NULL
                ORDER BY entry_time DESC, id DESC
                LIMIT 1
                """,
                (db_symbol, version),
            ).fetchone()
            if open_row:
                trade_id, entry_price = open_row
                pnl_pct = ((float(entry_price) - price) / float(entry_price) * 100.0) if entry_price else None
                dollar_pnl = (float(entry_price) - price) * qty if entry_price else None
                result = "TP" if (dollar_pnl or 0) > 0 else "SL"
                conn.execute(
                    """
                    UPDATE trades
                    SET exit_time = ?, exit_price = ?, result = ?, pnl_pct = ?, dollar_pnl = ?
                    WHERE id = ?
                    """,
                    (ts, price, result, pnl_pct, dollar_pnl, trade_id),
                )
    return inserted


def _trade_one_symbol(conn: sqlite3.Connection, api: AlpacaLiveAPI, symbol: str, version: str, account_equity: float) -> None:
    # Evaluate both long and short for every symbol; match Pine's evaluation order (long first).
    order_symbol = _order_symbol(symbol)
    position = api.get_position(order_symbol)
    if position and abs(float(position.get("qty", 0.0) or 0.0)) > 0:
        _upsert_summary(conn, symbol, version, "holding", "existing open position", account_equity)
        print(f"HOLD {symbol}: existing position qty={position.get('qty')}")
        return

    open_orders = api.get_open_orders(order_symbol)
    if open_orders:
        _upsert_summary(conn, symbol, version, "waiting", f"{len(open_orders)} open order(s)", account_equity)
        print(f"WAIT {symbol}: open orders present")
        return

    df = fetch_ohlcv(symbol)
    long_analysis = _entry_analysis(df, side="long", version=version)
    short_analysis = _entry_analysis(df, side="short", version=version)

    if long_analysis.get("is_entry"):
        side = "long"
    elif short_analysis.get("is_entry") and _can_short_symbol(symbol):
        side = "short"
    else:
        long_detail = str(long_analysis.get("detail") or "no long signal")
        short_detail = str(short_analysis.get("detail") or "no short signal")
        _upsert_summary(conn, symbol, version, "idle", f"long: {long_detail} | short: {short_detail}", account_equity)
        print(f"IDLE {symbol}: long: {long_detail} | short: {short_detail}")
        return

    # Broker constraint: Alpaca live does not support crypto spot shorts.
    if side == "short" and not _can_short_symbol(symbol):
        detail = "short signal detected but crypto short not supported on Alpaca live"
        _upsert_summary(conn, symbol, version, "idle", detail, account_equity)
        print(f"IDLE {symbol}: {detail}")
        return

    portfolio_decision = evaluate_trade(
        symbol,
        side,
        df,
        portfolio_cfg=_strategy_params(version).get("portfolio", {}),
    )
    if not portfolio_decision.allow_trade:
        detail = f"portfolio_filter: {portfolio_decision.reason}"
        _upsert_summary(conn, symbol, version, "portfolio_filter", detail, account_equity)
        print(f"SKIP {symbol}: {detail}")
        return

    order_params = _compute_order_params(
        df,
        account_equity,
        side=side,
        version=version,
        risk_multiplier=portfolio_decision.risk_multiplier,
    )
    if not order_params:
        _upsert_summary(conn, symbol, version, "idle", "insufficient data/invalid ATR", account_equity)
        print(f"IDLE {symbol}: invalid order params")
        return

    qty, tp, sl = order_params
    try:
        if side == "long":
            order = api.submit_long_bracket(symbol=order_symbol, qty=qty, take_profit=tp, stop_loss=sl)
        else:
            order = api.submit_short_bracket(symbol=order_symbol, qty=qty, take_profit=tp, stop_loss=sl)
        order_id = order.get("id") if isinstance(order, dict) else None
        _upsert_summary(conn, symbol, version, "submitted", f"{side} bracket submitted order_id={order_id}", account_equity)
        print(f"SUBMIT {symbol}: side={side} qty={qty} tp={tp:.4f} sl={sl:.4f}")
    except Exception as exc:
        _upsert_summary(conn, symbol, version, "error", str(exc), account_equity)
        print(f"ERROR {symbol}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run realtime Alpaca LIVE trading for APM versions.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--symbol", help="Trading symbol, e.g. CLM")
    scope.add_argument("--all-symbols", action="store_true", help="Run for every symbol in the DB")
    parser.add_argument("--version", required=True, help="Strategy version (v1-v6)")
    args = parser.parse_args()

    if os.getenv("ALLOW_ALPACA_LIVE_TRADING", "false").strip().lower() not in {"1", "true", "yes"}:
        print(
            "Live trading safety lock is enabled. Set ALLOW_ALPACA_LIVE_TRADING=true to allow live order placement.",
            file=sys.stderr,
        )
        return 2

    version = args.version.strip().lower()
    if version not in VERSION_MAP:
        print(f"Unsupported version {version!r}. Valid: {list(VERSION_MAP)}", file=sys.stderr)
        return 1

    symbols = [args.symbol.strip()] if args.symbol else _load_symbols_from_db()
    if not symbols:
        print("No symbols found in DB")
        return 0

    api = AlpacaLiveAPI()
    account = api.get_account()
    account_equity = float(account.get("equity") or account.get("last_equity") or 100000.0)

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=DELETE")
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass

    failures: list[str] = []
    for symbol in symbols:
        try:
            _trade_one_symbol(conn, api, symbol, version, account_equity)
        except Exception as exc:
            failures.append(symbol)
            _upsert_summary(conn, symbol, version, "error", str(exc), account_equity)
            print(f"ERROR {symbol}: {exc}")

    fill_count = _sync_fill_events(conn, api, symbols, version)
    print(f"Synced live fill activities: {fill_count}")

    conn.commit()
    conn.close()

    if failures:
        print(f"Realtime live trading failures: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
