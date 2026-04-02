from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SG_DIR = BACKEND_DIR / "strategy_generator"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SG_DIR))

from live_trading import realtime_alpaca_live_trader as live  # noqa: E402
from portfolio_system import evaluate_trade  # noqa: E402

SAMPLE_CSV = REPO_ROOT / "backend" / "data" / "btc_usd_5m_ytd.csv"
VERSIONS = ("v1", "v2", "v3", "v4", "v5", "v6")
ACCOUNT_EQUITY = 100000.0


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _load_sample() -> pd.DataFrame:
    if not SAMPLE_CSV.exists():
        raise FileNotFoundError(f"Missing sample CSV: {SAMPLE_CSV}")

    df = pd.read_csv(SAMPLE_CSV)
    if len(df) < 400:
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
    return df.head(400).copy()


def _validation_target(version: str) -> tuple[str, str]:
    params = live._strategy_params(version)
    signal = params.get("signal", {})
    enable_longs = bool(signal.get("enable_longs", False))
    enable_shorts = bool(signal.get("enable_shorts", True))

    if enable_longs and not enable_shorts:
        return "BTC/USD", "long"
    if enable_longs and enable_shorts:
        return "BTC/USD", "long"
    return "CLM", "short"


def main() -> int:
    try:
        base_df = _load_sample()
    except Exception as exc:
        return fail(str(exc))

    for version in VERSIONS:
        symbol, side = _validation_target(version)
        enriched_df = base_df.copy()

        try:
            entry = live._entry_analysis(enriched_df, side=side, version=version)
        except Exception as exc:
            return fail(f"entry analysis failed for {version}: {exc}")

        if not isinstance(entry, dict):
            return fail(f"entry analysis did not return dict for {version}")
        if "atr" not in enriched_df.columns:
            return fail(f"entry analysis did not populate atr for {version}")

        portfolio_cfg = live._strategy_params(version).get("portfolio", {})
        try:
            decision = evaluate_trade(symbol, side, enriched_df, portfolio_cfg=portfolio_cfg)
        except Exception as exc:
            return fail(f"portfolio evaluation failed for {version}: {exc}")

        risk_multiplier = decision.risk_multiplier if decision.allow_trade else 1.0
        try:
            order_params = live._compute_order_params(
                enriched_df,
                ACCOUNT_EQUITY,
                side=side,
                version=version,
                risk_multiplier=risk_multiplier,
            )
        except Exception as exc:
            return fail(f"order param calculation failed for {version}: {exc}")

        if order_params is None:
            return fail(f"order param calculation returned None for {version}")

        qty, tp, sl = order_params
        if qty <= 0:
            return fail(f"non-positive qty for {version}: {qty}")
        if side == "long" and not (tp > sl):
            return fail(f"invalid long bracket ordering for {version}: tp={tp}, sl={sl}")
        if side == "short" and not (sl > tp):
            return fail(f"invalid short bracket ordering for {version}: tp={tp}, sl={sl}")

        print(
            f"OK {version}: symbol={symbol} side={side} qty={qty:.6f} "
            f"portfolio_allow={decision.allow_trade} reason={decision.reason}"
        )

    print("Live dry version validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
