from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

from backtest_backtrader_alpaca import fetch_ohlcv, run_backtest  # noqa: E402


WIN_RATE_TARGET = 70.0
NET_RETURN_TARGET = 20.0
MAX_DD_TARGET = 4.5


@dataclass
class SymbolResult:
    symbol: str
    asset_class: str
    trades: int
    win_rate: float
    net_return_pct: float
    max_drawdown_pct: float

    @property
    def pass_win_rate(self) -> bool:
        return self.win_rate >= WIN_RATE_TARGET

    @property
    def pass_net_return(self) -> bool:
        return self.net_return_pct >= NET_RETURN_TARGET

    @property
    def pass_drawdown(self) -> bool:
        return self.max_drawdown_pct <= MAX_DD_TARGET

    @property
    def pass_all(self) -> bool:
        return self.pass_win_rate and self.pass_net_return and self.pass_drawdown


def classify_asset(symbol: str) -> str:
    return "crypto" if "/" in symbol else "stocks"


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def load_default_symbols(symbols_json_path: Path) -> list[str]:
    if not symbols_json_path.exists():
        return ["BTC/USD", "ETH/USD", "CLM", "CRF"]

    data = json.loads(symbols_json_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return ["BTC/USD", "ETH/USD", "CLM", "CRF"]

    symbols: list[str] = []
    seen: set[str] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue
        key = normalize_symbol(symbol)
        if key in seen:
            continue
        seen.add(key)
        symbols.append(symbol)

    return symbols or ["BTC/USD", "ETH/USD", "CLM", "CRF"]


def filter_symbols(symbols: list[str], asset_class: str) -> list[str]:
    if asset_class == "all":
        return symbols
    return [s for s in symbols if classify_asset(s) == asset_class]


def compute_result(symbol: str, version: str, profile: str | None) -> SymbolResult:
    df = fetch_ohlcv(symbol)
    trades = run_backtest(df, version, symbol=symbol, profile=profile)

    if trades.empty:
        return SymbolResult(
            symbol=symbol,
            asset_class=classify_asset(symbol),
            trades=0,
            win_rate=0.0,
            net_return_pct=0.0,
            max_drawdown_pct=0.0,
        )

    start_equity = float(trades["equity"].iloc[0] - trades["pnl"].iloc[0])
    win_rate = float((trades["pnl"] > 0).mean() * 100.0)
    net_return = float((trades["equity"].iloc[-1] / start_equity - 1.0) * 100.0) if start_equity else 0.0

    equity = trades["equity"].astype(float)
    max_dd = float(((equity.cummax() - equity) / equity.cummax() * 100.0).max())
    if math.isnan(max_dd):
        max_dd = 0.0

    return SymbolResult(
        symbol=symbol,
        asset_class=classify_asset(symbol),
        trades=int(len(trades)),
        win_rate=win_rate,
        net_return_pct=net_return,
        max_drawdown_pct=max_dd,
    )


def fmt_pass(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def print_symbol_table(results: list[SymbolResult]) -> None:
    print("\n=== Per-Symbol Guideline Matrix ===")
    header = (
        f"{'SYMBOL':<10} {'CLASS':<7} {'TRADES':>6} "
        f"{'WR%':>8} {'NET%':>8} {'MAXDD%':>8} "
        f"{'WR':>5} {'NET':>5} {'DD':>5} {'ALL':>5}"
    )
    print(header)
    print("-" * len(header))
    for row in results:
        print(
            f"{row.symbol:<10} {row.asset_class:<7} {row.trades:>6} "
            f"{row.win_rate:>8.2f} {row.net_return_pct:>8.2f} {row.max_drawdown_pct:>8.2f} "
            f"{fmt_pass(row.pass_win_rate):>5} {fmt_pass(row.pass_net_return):>5} "
            f"{fmt_pass(row.pass_drawdown):>5} {fmt_pass(row.pass_all):>5}"
        )


def summarize_group(name: str, rows: list[SymbolResult]) -> None:
    if not rows:
        print(f"\n{name}: no symbols")
        return

    pass_all = sum(1 for r in rows if r.pass_all)
    avg_wr = sum(r.win_rate for r in rows) / len(rows)
    avg_net = sum(r.net_return_pct for r in rows) / len(rows)
    avg_dd = sum(r.max_drawdown_pct for r in rows) / len(rows)

    print(
        f"\n{name}: symbols={len(rows)} pass_all={pass_all}/{len(rows)} "
        f"avg_wr={avg_wr:.2f}% avg_net={avg_net:.2f}% avg_dd={avg_dd:.2f}%"
    )


def to_json_payload(version: str, profile: str | None, results: list[SymbolResult]) -> dict:
    by_class: dict[str, list[SymbolResult]] = {
        "crypto": [r for r in results if r.asset_class == "crypto"],
        "stocks": [r for r in results if r.asset_class == "stocks"],
    }

    def cls_summary(rows: list[SymbolResult]) -> dict:
        if not rows:
            return {"symbols": 0, "pass_all": 0, "avg_wr": 0.0, "avg_net": 0.0, "avg_dd": 0.0}
        return {
            "symbols": len(rows),
            "pass_all": sum(1 for r in rows if r.pass_all),
            "avg_wr": sum(r.win_rate for r in rows) / len(rows),
            "avg_net": sum(r.net_return_pct for r in rows) / len(rows),
            "avg_dd": sum(r.max_drawdown_pct for r in rows) / len(rows),
        }

    return {
        "version": version,
        "profile": profile,
        "guidelines": {
            "win_rate_min": WIN_RATE_TARGET,
            "net_return_min": NET_RETURN_TARGET,
            "max_drawdown_max": MAX_DD_TARGET,
        },
        "symbols": [
            {
                "symbol": r.symbol,
                "asset_class": r.asset_class,
                "trades": r.trades,
                "win_rate": r.win_rate,
                "net_return_pct": r.net_return_pct,
                "max_drawdown_pct": r.max_drawdown_pct,
                "pass_win_rate": r.pass_win_rate,
                "pass_net_return": r.pass_net_return,
                "pass_drawdown": r.pass_drawdown,
                "pass_all": r.pass_all,
            }
            for r in results
        ],
        "summary": {
            "overall": cls_summary(results),
            "crypto": cls_summary(by_class["crypto"]),
            "stocks": cls_summary(by_class["stocks"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run v2 backtests and print a strategy-guideline matrix by symbol/class.")
    parser.add_argument("--version", default="v2", help="Strategy version (default: v2)")
    parser.add_argument("--profile", help="Optional v2 runtime profile, e.g. eth_focus")
    parser.add_argument(
        "--asset-class",
        choices=["all", "crypto", "stocks"],
        default="all",
        help="Filter symbols by asset class (default: all)",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="Optional explicit symbol list. If omitted, uses docs/data/symbols.json",
    )
    parser.add_argument("--json-out", help="Optional output path for JSON report")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when any selected symbol fails guideline thresholds.",
    )
    args = parser.parse_args()

    symbols = args.symbols if args.symbols else load_default_symbols(REPO_ROOT / "docs" / "data" / "symbols.json")
    symbols = filter_symbols(symbols, args.asset_class)

    if not symbols:
        print("No symbols selected.")
        return 1

    print(
        f"Running guideline matrix for version={args.version}, "
        f"profile={args.profile or 'default'}, asset_class={args.asset_class}"
    )

    results: list[SymbolResult] = []
    for symbol in symbols:
        try:
            results.append(compute_result(symbol, args.version, args.profile))
        except Exception as exc:
            print(f"ERROR {symbol}: {exc}", file=sys.stderr)

    if not results:
        print("No successful backtests.")
        return 2

    print_symbol_table(results)
    summarize_group("overall", results)
    summarize_group("crypto", [r for r in results if r.asset_class == "crypto"])
    summarize_group("stocks", [r for r in results if r.asset_class == "stocks"])

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = to_json_payload(args.version, args.profile, results)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {out_path}")

    if args.enforce:
        failing = [r for r in results if not r.pass_all]
        if failing:
            print("\nGuideline enforcement FAILED for:", file=sys.stderr)
            for row in failing:
                print(
                    f"  - {row.symbol}: "
                    f"WR={row.win_rate:.2f}% NET={row.net_return_pct:.2f}% DD={row.max_drawdown_pct:.2f}%",
                    file=sys.stderr,
                )
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
