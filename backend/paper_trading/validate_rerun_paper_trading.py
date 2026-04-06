from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

from paper_trading import realtime_alpaca_paper_trader as paper  # noqa: E402
from portfolio_system import PortfolioDecision  # noqa: E402

SAMPLE_CSV = REPO_ROOT / "backend" / "data" / "btc_usd_5m_ytd.csv"
BASE_DB = REPO_ROOT / "docs" / "data" / "tradingcopilot.db"
ACCOUNT_EQUITY = 100000.0


@dataclass(frozen=True)
class ValidationTarget:
    symbol: str
    version: str
    side: str


TARGETS = (
    ValidationTarget(symbol="BTC/USDT", version="v2", side="long"),
    ValidationTarget(symbol="CLM", version="v6", side="short"),
)


class FakeAlpacaPaperAPI:
    def __init__(self) -> None:
        self.orders: list[dict[str, object]] = []
        self.fills: list[dict[str, object]] = []

    def get_account(self) -> dict[str, object]:
        return {
            "id": "paper-account",
            "account_number": "paper-sim",
            "currency": "USD",
            "status": "ACTIVE",
            "equity": ACCOUNT_EQUITY,
            "last_equity": ACCOUNT_EQUITY,
            "cash": ACCOUNT_EQUITY,
            "buying_power": ACCOUNT_EQUITY * 2,
        }

    def get_open_orders(self, symbol: str) -> list[dict[str, object]]:
        return [order for order in self.orders if str(order.get("symbol")) == symbol]

    def get_closed_orders(self, *, after: str | None = None, limit: int = 200) -> list[dict[str, object]]:
        return []

    def get_position(self, symbol: str) -> dict[str, object] | None:
        return None

    def list_positions(self) -> list[dict[str, object]]:
        return []

    def close_position(self, symbol: str) -> dict[str, object]:
        return {"symbol": symbol, "status": "closed"}

    def submit_long_bracket(self, *, symbol: str, qty: float, take_profit: float, stop_loss: float) -> dict[str, object]:
        order = {
            "id": f"dry-long-{len(self.orders) + 1}",
            "symbol": symbol,
            "side": "buy",
            "qty": qty,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
        }
        self.orders.append(order)
        return order

    def submit_short_bracket(self, *, symbol: str, qty: float, take_profit: float, stop_loss: float) -> dict[str, object]:
        order = {
            "id": f"dry-short-{len(self.orders) + 1}",
            "symbol": symbol,
            "side": "sell",
            "qty": qty,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
        }
        self.orders.append(order)
        return order

    def get_fill_activities(self, *, after: str | None = None) -> list[dict[str, object]]:
        return list(self.fills)


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _load_sample() -> pd.DataFrame:
    if not SAMPLE_CSV.exists():
        raise FileNotFoundError(f"Missing sample CSV: {SAMPLE_CSV}")

    df = pd.read_csv(SAMPLE_CSV).head(400).copy()
    if len(df) < 210:
        raise RuntimeError(f"Sample CSV has insufficient rows: {len(df)}")

    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    required = {"timestamp", "Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Sample CSV missing required columns: {missing}")
    return df


def _validate_analysis_dispatch(target: ValidationTarget, base_df: pd.DataFrame) -> None:
    entry_df = base_df.copy()
    entry = paper._entry_analysis(entry_df, side=target.side, version=target.version, symbol=target.symbol)
    if not isinstance(entry, dict):
        raise RuntimeError(f"entry analysis did not return dict for {target.symbol} {target.version}")

    exit_df = base_df.copy()
    exit_result = paper._exit_analysis(exit_df, side=target.side, version=target.version, symbol=target.symbol)
    if not isinstance(exit_result, dict):
        raise RuntimeError(f"exit analysis did not return dict for {target.symbol} {target.version}")

    params_df = base_df.copy()
    paper._entry_analysis(params_df, side=target.side, version=target.version, symbol=target.symbol)
    order_params = paper._compute_order_params(
        params_df,
        ACCOUNT_EQUITY,
        side=target.side,
        version=target.version,
        symbol=target.symbol,
        risk_multiplier=1.0,
    )
    if order_params is None:
        raise RuntimeError(f"order param calculation returned None for {target.symbol} {target.version}")


def _forced_entry_analysis_factory(target: ValidationTarget):
    def _forced_entry_analysis(df, side: str, version: str, symbol: str | None = None) -> dict[str, object]:
        return {
            "is_entry": side == target.side,
            "is_near_miss": False,
            "detail": f"dry rerun validation {target.side}",
            "latest_bar_ts": paper._latest_bar_timestamp(df),
            "passed_stage": "dry_validation",
        }

    return _forced_entry_analysis


def _forced_order_params(side: str) -> tuple[float, float, float]:
    if side == "long":
        return (1.0, 110.0, 90.0)
    return (1.0, 90.0, 110.0)


def _assert_summary(conn: sqlite3.Connection, target: ValidationTarget) -> None:
    row = conn.execute(
        "SELECT metrics, notes FROM paper_trading_results WHERE symbol = ? AND notes LIKE ? LIMIT 1",
        (target.symbol, f"%{paper.VERSION_MAP.get(target.version, target.version)} realtime alpaca%"),
    ).fetchone()
    if not row:
        raise RuntimeError(f"missing realtime paper summary for {target.symbol} {target.version}")

    metrics = json.loads(str(row[0] or "{}"))
    if metrics.get("status") != "submitted":
        raise RuntimeError(
            f"unexpected summary status for {target.symbol} {target.version}: {metrics.get('status')!r}"
        )


def _assert_realtime_trade(conn: sqlite3.Connection, target: ValidationTarget) -> None:
    row = conn.execute(
        """
        SELECT direction, result, source
        FROM trades
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
          AND LOWER(version) = ?
          AND mode = 'paper'
        ORDER BY id DESC
        LIMIT 1
        """,
        ("".join(ch for ch in target.symbol.upper() if ch.isalnum()), target.version),
    ).fetchone()
    if not row:
        raise RuntimeError(f"missing paper trade row for {target.symbol} {target.version}")

    direction, result, source = row
    if str(direction).lower() != target.side:
        raise RuntimeError(
            f"unexpected trade direction for {target.symbol} {target.version}: {direction!r}"
        )
    if str(result).upper() != "OPEN":
        raise RuntimeError(f"unexpected trade result for {target.symbol} {target.version}: {result!r}")
    if str(source).lower() != "realtime":
        raise RuntimeError(f"unexpected trade source for {target.symbol} {target.version}: {source!r}")


def _exercise_dry_rerun(temp_db: Path, target: ValidationTarget, base_df: pd.DataFrame) -> None:
    conn = sqlite3.connect(str(temp_db), timeout=30)
    conn.execute("PRAGMA journal_mode=DELETE")
    paper._ensure_source_column(conn)

    api = FakeAlpacaPaperAPI()
    event_time = datetime.now(UTC).isoformat()

    original_fetch = paper.fetch_ohlcv
    original_entry = paper._entry_analysis
    original_eval = paper.evaluate_trade
    original_compute = paper._compute_order_params
    original_db_path = paper.DB_PATH

    try:
        paper.fetch_ohlcv = lambda symbol: base_df.copy()
        paper._entry_analysis = _forced_entry_analysis_factory(target)
        paper.evaluate_trade = lambda *args, **kwargs: PortfolioDecision(True, "ok", 1.0, 4)
        paper._compute_order_params = lambda *args, **kwargs: _forced_order_params(kwargs.get("side", target.side))
        paper.DB_PATH = temp_db

        submitted, diag = paper._trade_one_symbol(conn, api, target.symbol, target.version, ACCOUNT_EQUITY)
        if not submitted:
            raise RuntimeError(f"dry rerun did not submit for {target.symbol} {target.version}: {diag}")

        order = api.orders[-1]
        api.fills = [
            {
                "id": f"fill-{order['id']}",
                "symbol": order["symbol"],
                "side": order["side"],
                "qty": order["qty"],
                "price": 100.0,
                "transaction_time": event_time,
                "order_id": order["id"],
            }
        ]

        fill_count = paper._sync_fill_events(conn, api, [target.symbol], target.version, ACCOUNT_EQUITY)
        if fill_count != 1:
            raise RuntimeError(f"expected one fill event for {target.symbol} {target.version}, got {fill_count}")

        cancel_count = paper._sync_canceled_orders(conn, api, [target.symbol])
        if cancel_count != 0:
            raise RuntimeError(f"expected zero cancel events for {target.symbol} {target.version}, got {cancel_count}")

        conn.commit()
        _assert_summary(conn, target)
        _assert_realtime_trade(conn, target)

        print(
            f"OK {target.version}: symbol={target.symbol} side={target.side} order_id={order['id']} fill_count={fill_count}"
        )
    finally:
        paper.fetch_ohlcv = original_fetch
        paper._entry_analysis = original_entry
        paper.evaluate_trade = original_eval
        paper._compute_order_params = original_compute
        paper.DB_PATH = original_db_path
        conn.close()


def main() -> int:
    if not BASE_DB.exists():
        return fail(f"Missing base DB: {BASE_DB}")

    try:
        base_df = _load_sample()
    except Exception as exc:
        return fail(str(exc))

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db = Path(temp_dir) / BASE_DB.name
        shutil.copy2(BASE_DB, temp_db)

        try:
            for target in TARGETS:
                _validate_analysis_dispatch(target, base_df)
                _exercise_dry_rerun(temp_db, target, base_df)
        except Exception as exc:
            return fail(str(exc))

    print("Rerun paper trading validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())