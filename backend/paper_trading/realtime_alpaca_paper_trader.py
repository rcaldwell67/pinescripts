"""
Real-time Alpaca Paper Trading runner for APM v1.

This script evaluates the latest signal for each symbol and, when eligible,
submits a paper bracket order to Alpaca. It also syncs recent fill
activities back into tradingcopilot.db so the dashboard can show real paper
trade events.

Usage:
    python backend/paper_trading/realtime_alpaca_paper_trader.py --all-symbols --version v1
    python backend/paper_trading/realtime_alpaca_paper_trader.py --symbol CLM --version v1
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

from apm_v1 import apm_v1_signals
from backtest_backtrader_alpaca import DB_PATH, VERSION_MAP, fetch_ohlcv
from v1_params import get_v1_params

ALPACA_BASE = "https://paper-api.alpaca.markets"
V1_PARAMS = get_v1_params()


class AlpacaBarStreamer:
    """Optional live bar streamer for event-driven symbol checks."""

    def __init__(self) -> None:
        self._threads: list[Thread] = []
        self._streams: list[Any] = []
        self._pending: dict[str, bool] = defaultdict(bool)
        self._lock = Lock()
        self._stop = Event()

    def _mark_symbol(self, symbol: str) -> None:
        with self._lock:
            self._pending[symbol] = True

    def drain_ready_symbols(self) -> list[str]:
        with self._lock:
            ready = [s for s, v in self._pending.items() if v]
            for s in ready:
                self._pending[s] = False
            return ready

    def start(self, symbols: list[str]) -> bool:
        key = os.getenv("ALPACA_PAPER_API_KEY") or os.getenv("ALPACA_API_KEY")
        secret = os.getenv("ALPACA_PAPER_API_SECRET") or os.getenv("ALPACA_API_SECRET")
        if not key or not secret:
            return False

        try:
            from alpaca.data.live import CryptoDataStream, StockDataStream
        except Exception:
            return False

        crypto_symbols = [s for s in symbols if "/" in s]
        stock_symbols = [s for s in symbols if "/" not in s]

        if stock_symbols:
            stock_stream = StockDataStream(key, secret)

            async def _stock_bar(bar) -> None:
                symbol = str(getattr(bar, "symbol", "") or "")
                if symbol:
                    self._mark_symbol(symbol)

            stock_stream.subscribe_bars(_stock_bar, *stock_symbols)
            self._streams.append(stock_stream)

        if crypto_symbols:
            crypto_stream = CryptoDataStream(key, secret)

            async def _crypto_bar(bar) -> None:
                symbol = str(getattr(bar, "symbol", "") or "")
                if symbol:
                    self._mark_symbol(symbol)

            crypto_stream.subscribe_bars(_crypto_bar, *crypto_symbols)
            self._streams.append(crypto_stream)

        if not self._streams:
            return False

        for stream in self._streams:
            t = Thread(target=stream.run, daemon=True)
            t.start()
            self._threads.append(t)
        return True

    def stop(self) -> None:
        self._stop.set()
        for stream in self._streams:
            try:
                stream.stop()
            except Exception:
                pass


class AlpacaPaperAPI:
    def __init__(self) -> None:
        key = os.getenv("ALPACA_PAPER_API_KEY") or os.getenv("ALPACA_API_KEY")
        secret = os.getenv("ALPACA_PAPER_API_SECRET") or os.getenv("ALPACA_API_SECRET")
        if not key or not secret:
            raise RuntimeError("Missing Alpaca credentials. Set ALPACA_PAPER_API_KEY and ALPACA_PAPER_API_SECRET.")

        self.headers = {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
        url = f"{ALPACA_BASE}{path}"
        resp = requests.request(method, url, headers=self.headers, params=params, json=payload, timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Alpaca {method} {path} failed: {resp.status_code} {resp.text}")
        if not resp.text:
            return None
        return resp.json()

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def get_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        params = {"status": "open", "symbols": symbol, "direction": "desc", "limit": 50}
        data = self._request("GET", "/v2/orders", params=params)
        return data if isinstance(data, list) else []

    def get_closed_orders(self, *, after: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"status": "closed", "direction": "desc", "limit": limit}
        if after:
            params["after"] = after
        data = self._request("GET", "/v2/orders", params=params)
        return data if isinstance(data, list) else []

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/v2/positions/{symbol}")
        except RuntimeError as exc:
            if "404" in str(exc):
                return None
            raise

    def list_positions(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/v2/positions")
        return data if isinstance(data, list) else []

    def close_position(self, symbol: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v2/positions/{symbol}")

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
    # Alpaca trading endpoints use BTCUSD-style symbols for crypto.
    return symbol.replace("/", "")


def _load_symbols_from_db() -> list[str]:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    rows = conn.execute("SELECT symbol FROM symbols ORDER BY symbol").fetchall()
    conn.close()
    return [row[0] for row in rows]


def _latest_signal_is_entry(df) -> bool:
    entries = set(apm_v1_signals(df, params=V1_PARAMS))
    if not entries:
        return False
    return (len(df) - 1) in entries


def _target_side_for_symbol(symbol: str) -> str:
    # Alpaca paper supports long crypto, but spot shorting is not supported.
    return "long" if "/" in symbol else "short"


def _compute_order_params(df, account_equity: float, side: str) -> tuple[float, float, float] | None:
    risk = V1_PARAMS["risk"]
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

    risk_budget = max(account_equity * float(risk["risk_pct"]) / 100.0, 1.0)
    qty = round(risk_budget / risk_per_unit, 6)
    if qty <= 0:
        return None

    return qty, tp, sl


def _upsert_summary(conn: sqlite3.Connection, symbol: str, version: str, status: str, detail: str, equity: float | None) -> None:
    notes = f"{VERSION_MAP.get(version, version)} realtime alpaca summary"
    metrics = {
        "symbol": symbol,
        "version": version,
        "status": status,
        "detail": detail,
        "equity": equity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(
        "DELETE FROM paper_trading_results WHERE symbol = ? AND notes LIKE ?",
        (symbol, f"%{VERSION_MAP.get(version, version)} realtime alpaca%"),
    )
    conn.execute(
        "INSERT INTO paper_trading_results (symbol, metrics, notes) VALUES (?, ?, ?)",
        (symbol, json.dumps(metrics), notes),
    )


def _ensure_account_info_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS Account_Info (
            account_id TEXT PRIMARY KEY,
            account_number TEXT,
            currency TEXT,
            status TEXT,
            beginning_balance REAL,
            current_balance REAL,
            buying_power REAL,
            cash REAL,
            last_event TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _upsert_account_info(conn: sqlite3.Connection, account: dict[str, Any], *, event_type: str) -> None:
    _ensure_account_info_table(conn)
    account_id = str(account.get("id") or "paper-account")
    account_number = str(account.get("account_number") or "")
    currency = str(account.get("currency") or "USD")
    status = str(account.get("status") or "")
    current_balance = _to_float(account.get("equity") or account.get("last_equity") or account.get("cash"), 0.0)
    buying_power = _to_float(account.get("buying_power"), 0.0)
    cash = _to_float(account.get("cash"), 0.0)

    existing = conn.execute(
        "SELECT beginning_balance FROM Account_Info WHERE account_id = ? LIMIT 1",
        (account_id,),
    ).fetchone()
    beginning_balance = _to_float(existing[0], current_balance) if existing else current_balance

    conn.execute(
        """
        INSERT INTO Account_Info (
            account_id, account_number, currency, status,
            beginning_balance, current_balance, buying_power, cash, last_event, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            account_number = excluded.account_number,
            currency = excluded.currency,
            status = excluded.status,
            beginning_balance = Account_Info.beginning_balance,
            current_balance = excluded.current_balance,
            buying_power = excluded.buying_power,
            cash = excluded.cash,
            last_event = excluded.last_event,
            updated_at = excluded.updated_at
        """,
        (
            account_id,
            account_number,
            currency,
            status,
            beginning_balance,
            current_balance,
            buying_power,
            cash,
            event_type,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def _ensure_fill_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_fill_events (
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
        CREATE TABLE IF NOT EXISTS paper_order_trade_links (
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
        CREATE TABLE IF NOT EXISTS paper_order_events (
            event_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            symbol TEXT,
            status TEXT,
            event_type TEXT,
            event_time TEXT,
            raw_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _fill_exists(conn: sqlite3.Connection, activity_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM paper_fill_events WHERE activity_id = ? LIMIT 1", (activity_id,)).fetchone()
    return bool(row)


def _link_order_to_trade(conn: sqlite3.Connection, order_id: str, symbol: str, version: str, trade_id: int, role: str) -> None:
    if not order_id:
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO paper_order_trade_links (order_id, symbol, version, trade_id, role)
        VALUES (?, ?, ?, ?, ?)
        """,
        (order_id, symbol, version, trade_id, role),
    )


def _trade_for_order(conn: sqlite3.Connection, order_id: str) -> tuple[int, str] | None:
    if not order_id:
        return None
    row = conn.execute(
        "SELECT trade_id, role FROM paper_order_trade_links WHERE order_id = ? LIMIT 1",
        (order_id,),
    ).fetchone()
    if not row:
        return None
    return int(row[0]), str(row[1])


def _get_last_known_equity(conn: sqlite3.Connection, symbol: str, version: str, fallback_equity: float) -> float:
    row = conn.execute(
        """
        SELECT equity
        FROM trades
        WHERE symbol = ? AND version = ? AND mode = 'paper' AND equity IS NOT NULL
        ORDER BY COALESCE(exit_time, entry_time) DESC, id DESC
        LIMIT 1
        """,
        (symbol, version),
    ).fetchone()
    if row and row[0] is not None:
        return float(row[0])
    return float(fallback_equity)


def _sync_fill_events(
    conn: sqlite3.Connection,
    api: AlpacaPaperAPI,
    symbols: list[str],
    version: str,
    account_equity: float,
) -> int:
    _ensure_fill_table(conn)
    row = conn.execute("SELECT MAX(transaction_time) FROM paper_fill_events").fetchone()
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
        if _fill_exists(conn, act_id):
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO paper_fill_events (
                activity_id, symbol, side, qty, price, transaction_time, order_id, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (act_id, db_symbol, side, qty, price, ts, order_id, json.dumps(fill)),
        )
        inserted += 1

        # Mirror fills into trades table for dashboard visibility.
        # buy can open long or close short; sell can open short or close long.
        linked = _trade_for_order(conn, order_id)

        if side == "buy":
            close_row = None
            if linked and linked[1] == "exit":
                close_row = conn.execute(
                    "SELECT id, entry_price, equity FROM trades WHERE id = ? LIMIT 1",
                    (linked[0],),
                ).fetchone()
            if not close_row:
                close_row = conn.execute(
                    """
                    SELECT id, entry_price, equity
                    FROM trades
                    WHERE symbol = ? AND version = ? AND mode = 'paper' AND direction = 'short' AND exit_time IS NULL
                    ORDER BY entry_time DESC, id DESC
                    LIMIT 1
                    """,
                    (db_symbol, version),
                ).fetchone()

            if close_row:
                trade_id, entry_price, entry_equity = close_row
                pnl_pct = ((float(entry_price) - price) / float(entry_price) * 100.0) if entry_price else None
                dollar_pnl = (float(entry_price) - price) * qty if entry_price else None
                result = "TP" if (dollar_pnl or 0) > 0 else "SL"
                base_equity = float(entry_equity) if entry_equity is not None else _get_last_known_equity(conn, db_symbol, version, account_equity)
                close_equity = base_equity + (float(dollar_pnl) if dollar_pnl is not None else 0.0)
                conn.execute(
                    """
                    UPDATE trades
                    SET exit_time = ?, exit_price = ?, result = ?, pnl_pct = ?, dollar_pnl = ?, equity = ?
                    WHERE id = ?
                    """,
                    (ts, price, result, pnl_pct, dollar_pnl, close_equity, trade_id),
                )
                _link_order_to_trade(conn, order_id, db_symbol, version, int(trade_id), "exit")
            elif not (linked and linked[1] == "entry"):
                base_equity = _get_last_known_equity(conn, db_symbol, version, account_equity)
                cur = conn.execute(
                    """
                    INSERT INTO trades (
                        symbol, version, mode, entry_time, exit_time, direction,
                        entry_price, exit_price, result, pnl_pct, dollar_pnl, equity
                    ) VALUES (?, ?, 'paper', ?, NULL, 'long', ?, NULL, 'OPEN', NULL, NULL, ?)
                    """,
                    (db_symbol, version, ts, price, base_equity),
                )
                _link_order_to_trade(conn, order_id, db_symbol, version, int(cur.lastrowid), "entry")
        elif side == "sell":
            close_row = None
            if linked and linked[1] == "exit":
                close_row = conn.execute(
                    "SELECT id, entry_price, equity FROM trades WHERE id = ? LIMIT 1",
                    (linked[0],),
                ).fetchone()
            if not close_row:
                close_row = conn.execute(
                    """
                    SELECT id, entry_price, equity
                    FROM trades
                    WHERE symbol = ? AND version = ? AND mode = 'paper' AND direction = 'long' AND exit_time IS NULL
                    ORDER BY entry_time DESC, id DESC
                    LIMIT 1
                    """,
                    (db_symbol, version),
                ).fetchone()

            if close_row:
                trade_id, entry_price, entry_equity = close_row
                pnl_pct = ((price - float(entry_price)) / float(entry_price) * 100.0) if entry_price else None
                dollar_pnl = (price - float(entry_price)) * qty if entry_price else None
                result = "TP" if (dollar_pnl or 0) > 0 else "SL"
                base_equity = float(entry_equity) if entry_equity is not None else _get_last_known_equity(conn, db_symbol, version, account_equity)
                close_equity = base_equity + (float(dollar_pnl) if dollar_pnl is not None else 0.0)
                conn.execute(
                    """
                    UPDATE trades
                    SET exit_time = ?, exit_price = ?, result = ?, pnl_pct = ?, dollar_pnl = ?, equity = ?
                    WHERE id = ?
                    """,
                    (ts, price, result, pnl_pct, dollar_pnl, close_equity, trade_id),
                )
                _link_order_to_trade(conn, order_id, db_symbol, version, int(trade_id), "exit")
            elif not (linked and linked[1] == "entry"):
                base_equity = _get_last_known_equity(conn, db_symbol, version, account_equity)
                cur = conn.execute(
                    """
                    INSERT INTO trades (
                        symbol, version, mode, entry_time, exit_time, direction,
                        entry_price, exit_price, result, pnl_pct, dollar_pnl, equity
                    ) VALUES (?, ?, 'paper', ?, NULL, 'short', ?, NULL, 'OPEN', NULL, NULL, ?)
                    """,
                    (db_symbol, version, ts, price, base_equity),
                )
                _link_order_to_trade(conn, order_id, db_symbol, version, int(cur.lastrowid), "entry")

        if side in {"buy", "sell"}:
            try:
                _upsert_account_info(conn, api.get_account(), event_type=f"fill:{side}")
            except Exception:
                # Non-fatal: keep fill ingestion moving even if account refresh fails.
                pass
    return inserted


def _sync_canceled_orders(conn: sqlite3.Connection, api: AlpacaPaperAPI, symbols: list[str]) -> int:
    _ensure_fill_table(conn)
    row = conn.execute(
        "SELECT MAX(event_time) FROM paper_order_events WHERE event_type = 'cancel'"
    ).fetchone()
    after = row[0] if row and row[0] else None

    valid_symbols = {_order_symbol(s) for s in symbols}
    closed_orders = api.get_closed_orders(after=after, limit=200)
    inserted = 0
    cancel_statuses = {"canceled", "expired", "rejected"}

    for order in closed_orders:
        status = str(order.get("status") or "").lower().strip()
        if status not in cancel_statuses:
            continue
        symbol = str(order.get("symbol") or "").strip()
        if valid_symbols and symbol and symbol not in valid_symbols:
            continue
        order_id = str(order.get("id") or "").strip()
        event_time = (
            str(order.get("canceled_at") or "").strip()
            or str(order.get("updated_at") or "").strip()
            or str(order.get("submitted_at") or "").strip()
            or datetime.now(timezone.utc).isoformat()
        )
        if not order_id:
            continue
        event_id = f"{order_id}:{status}:{event_time}"
        exists = conn.execute(
            "SELECT 1 FROM paper_order_events WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        if exists:
            continue

        conn.execute(
            """
            INSERT INTO paper_order_events (
                event_id, order_id, symbol, status, event_type, event_time, raw_json
            ) VALUES (?, ?, ?, ?, 'cancel', ?, ?)
            """,
            (event_id, order_id, symbol, status, event_time, json.dumps(order)),
        )
        inserted += 1

    if inserted > 0:
        try:
            _upsert_account_info(conn, api.get_account(), event_type="cancel")
        except Exception:
            pass
    return inserted


def _trade_one_symbol(
    conn: sqlite3.Connection,
    api: AlpacaPaperAPI,
    symbol: str,
    version: str,
    account_equity: float,
    close_on_signal: bool = False,
) -> bool:
    side = _target_side_for_symbol(symbol)

    order_symbol = _order_symbol(symbol)
    position = api.get_position(order_symbol)
    if position and abs(float(position.get("qty", 0.0) or 0.0)) > 0:
        if close_on_signal:
            df = fetch_ohlcv(symbol)
            if _latest_signal_is_entry(df):
                try:
                    api.close_position(order_symbol)
                    _upsert_summary(conn, symbol, version, "closing", "signal-triggered position close", account_equity)
                    print(f"CLOSE {symbol}: signal-triggered close submitted")
                    return False
                except Exception as exc:
                    _upsert_summary(conn, symbol, version, "error", f"close failed: {exc}", account_equity)
                    print(f"ERROR {symbol}: close failed: {exc}")
                    return False
        _upsert_summary(conn, symbol, version, "holding", "existing open position", account_equity)
        print(f"HOLD {symbol}: existing position qty={position.get('qty')}")
        return False

    open_orders = api.get_open_orders(order_symbol)
    if open_orders:
        _upsert_summary(conn, symbol, version, "waiting", f"{len(open_orders)} open order(s)", account_equity)
        print(f"WAIT {symbol}: open orders present")
        return False

    df = fetch_ohlcv(symbol)
    if not _latest_signal_is_entry(df):
        _upsert_summary(conn, symbol, version, "idle", f"no fresh {side} entry signal", account_equity)
        print(f"IDLE {symbol}: no entry")
        return False

    order_params = _compute_order_params(df, account_equity, side=side)
    if not order_params:
        _upsert_summary(conn, symbol, version, "idle", "insufficient data/invalid ATR", account_equity)
        print(f"IDLE {symbol}: invalid order params")
        return False

    qty, tp, sl = order_params
    try:
        if side == "long":
            order = api.submit_long_bracket(symbol=order_symbol, qty=qty, take_profit=tp, stop_loss=sl)
        else:
            order = api.submit_short_bracket(symbol=order_symbol, qty=qty, take_profit=tp, stop_loss=sl)
        order_id = order.get("id") if isinstance(order, dict) else None
        _upsert_summary(conn, symbol, version, "submitted", f"{side} bracket submitted order_id={order_id}", account_equity)
        print(f"SUBMIT {symbol}: side={side} qty={qty} tp={tp:.4f} sl={sl:.4f}")
        return True
    except Exception as exc:
        _upsert_summary(conn, symbol, version, "error", str(exc), account_equity)
        print(f"ERROR {symbol}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run realtime Alpaca paper trading for APM v1.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--symbol", help="Trading symbol, e.g. CLM")
    scope.add_argument("--all-symbols", action="store_true", help="Run for every symbol in the DB")
    parser.add_argument("--version", required=True, help="Strategy version (currently v1)")
    parser.add_argument("--loop-seconds", type=int, default=0, help="If > 0, continuously monitor symbols every N seconds")
    parser.add_argument("--max-loops", type=int, default=0, help="Maximum loop iterations when looping (0 = run indefinitely)")
    parser.add_argument("--stream-bars", action="store_true", help="Use Alpaca websocket bars to trigger symbol evaluations")
    parser.add_argument("--max-open-positions", type=int, default=8, help="Portfolio cap for simultaneous open positions")
    parser.add_argument("--close-on-signal", action="store_true", help="Attempt position close when a fresh signal appears while holding")
    args = parser.parse_args()

    version = args.version.strip().lower()
    if version != "v1":
        print("Only v1 realtime paper trading is currently supported.", file=sys.stderr)
        return 1

    symbols = [args.symbol.strip()] if args.symbol else _load_symbols_from_db()
    if not symbols:
        print("No symbols found in DB")
        return 0

    api = AlpacaPaperAPI()
    streamer = AlpacaBarStreamer()
    stream_enabled = False
    if args.stream_bars:
        stream_enabled = streamer.start(symbols)
        if not stream_enabled:
            print("WARN: --stream-bars requested but websocket stream unavailable; using polling loop")

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=DELETE")
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass

    loop_count = 0
    failures: list[str] = []
    try:
        while True:
            loop_count += 1
            account = api.get_account()
            account_equity = float(account.get("equity") or account.get("last_equity") or 100000.0)
            _upsert_account_info(conn, account, event_type="heartbeat")
            print(f"\n[{datetime.now(timezone.utc).isoformat()}] Monitoring pass #{loop_count} (equity={account_equity:.2f})")

            symbols_this_pass = symbols
            if stream_enabled:
                # Drain symbols that received a new bar since last pass.
                ready = streamer.drain_ready_symbols()
                if ready:
                    ready_set = set(ready)
                    symbols_this_pass = [s for s in symbols if s in ready_set or _order_symbol(s) in ready_set]
                elif loop_count > 1:
                    # Wait briefly for live bars before doing a no-op cycle.
                    time.sleep(1)
                    if args.max_loops > 0 and loop_count >= args.max_loops:
                        break
                    continue

            position_rows = api.list_positions()
            open_symbols = {
                str(p.get("symbol") or "").strip()
                for p in position_rows
                if abs(float(p.get("qty") or 0.0)) > 0
            }

            for symbol in symbols_this_pass:
                try:
                    osym = _order_symbol(symbol)
                    if osym not in open_symbols and len(open_symbols) >= max(args.max_open_positions, 1):
                        _upsert_summary(conn, symbol, version, "risk_cap", "max open positions reached", account_equity)
                        print(f"SKIP {symbol}: max open positions reached")
                        continue

                    submitted = _trade_one_symbol(
                        conn,
                        api,
                        symbol,
                        version,
                        account_equity,
                        close_on_signal=args.close_on_signal,
                    )
                    if submitted:
                        open_symbols.add(osym)
                except Exception as exc:
                    failures.append(symbol)
                    _upsert_summary(conn, symbol, version, "error", str(exc), account_equity)
                    print(f"ERROR {symbol}: {exc}")

            fill_count = _sync_fill_events(conn, api, symbols, version, account_equity)
            cancel_count = _sync_canceled_orders(conn, api, symbols)
            print(f"Synced fill activities: {fill_count}")
            print(f"Synced cancel activities: {cancel_count}")
            conn.commit()

            if args.loop_seconds <= 0 and not stream_enabled:
                break
            if args.max_loops > 0 and loop_count >= args.max_loops:
                break
            sleep_secs = 1 if stream_enabled else max(args.loop_seconds, 1)
            time.sleep(sleep_secs)
    finally:
        streamer.stop()
        conn.close()

    if failures:
        print(f"Realtime paper trading failures: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
