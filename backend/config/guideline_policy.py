"""
Centralized guideline policy definitions for consistent enforcement across backend and dashboard.

This module defines strategy guideline thresholds and symbol/version-specific overrides.
Both Python backend checks and JavaScript dashboard audit logic should source from this policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GuidelineThresholds:
    """Default guideline thresholds for all strategies."""

    min_trades: int = 2
    min_win_rate_pct: float = 65.0
    min_net_return_pct: float = 15.0
    max_drawdown_pct: float = 4.5


@dataclass
class GuidelineOverride:
    """Override rules for a specific symbol/version combination."""

    waived_hard_checks: set[str]  # e.g. {"win_rate"} means win_rate is advisory only


# Default thresholds applied to all symbols/versions unless overridden.
DEFAULT_THRESHOLDS = GuidelineThresholds(
    min_trades=2,
    min_win_rate_pct=65.0,
    min_net_return_pct=15.0,
    max_drawdown_pct=4.5,
)

# Symbol/version-specific overrides.
# Key format: (normalized_symbol, version) where normalized_symbol is uppercase alphanumeric.
POLICY_OVERRIDES: dict[tuple[str, str], GuidelineOverride] = {
    ("BTCUSDC", "v1"): GuidelineOverride(waived_hard_checks={"win_rate"}),
    ("ETHUSDT", "v3"): GuidelineOverride(waived_hard_checks={"win_rate"}),
    ("ETHUSDC", "v3"): GuidelineOverride(waived_hard_checks={"trades"}),
    **{
        ("CLM", version): GuidelineOverride(waived_hard_checks={"trades"})
        for version in ("v1", "v2", "v3", "v4", "v5", "v6", "v7")
    },
    **{
        ("CRF", version): GuidelineOverride(waived_hard_checks={"trades"})
        for version in ("v1", "v2", "v3", "v4", "v5", "v6", "v7")
    },
}


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol to uppercase alphanumeric for policy lookup."""
    return "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())


def get_override(symbol: str, version: str) -> GuidelineOverride | None:
    """Look up policy override for symbol/version pair."""
    key = (normalize_symbol(symbol), str(version or "").lower())
    return POLICY_OVERRIDES.get(key)


def evaluate_backtest_guideline(
    symbol: str,
    version: str,
    trades: int | None,
    win_rate_pct: float | None,
    net_return_pct: float | None,
    max_drawdown_pct: float | None,
) -> tuple[bool, list[str]]:
    """
    Evaluate backtest results against guideline policy.

    Returns:
        (passed, reasons) where passed is True if all non-waived thresholds are met,
        and reasons lists any failures or waivers.
    """
    thresholds = DEFAULT_THRESHOLDS
    override = get_override(symbol, version)
    waived = override.waived_hard_checks if override else set()

    failures = []
    waivers = []

    checks = [
        ("trades", trades is None or trades < thresholds.min_trades, f"trades<{thresholds.min_trades}"),
        (
            "win_rate",
            win_rate_pct is None or win_rate_pct < thresholds.min_win_rate_pct,
            f"wr<{thresholds.min_win_rate_pct:.0f}",
        ),
        (
            "net_return",
            net_return_pct is None or net_return_pct < thresholds.min_net_return_pct,
            f"net<{thresholds.min_net_return_pct:.0f}",
        ),
        (
            "max_drawdown",
            max_drawdown_pct is None or max_drawdown_pct > thresholds.max_drawdown_pct,
            f"dd>{thresholds.max_drawdown_pct:.1f}",
        ),
    ]

    for check_key, failed, reason in checks:
        if not failed:
            continue
        if check_key in waived:
            waivers.append(f"{reason} (advisory)")
        else:
            failures.append(reason)

    passed = len(failures) == 0
    reasons = failures + waivers

    return passed, reasons


def to_js_config() -> dict[str, Any]:
    """Generate JavaScript-compatible config from this policy."""
    return {
        "GUIDELINE_THRESHOLDS": {
            "minTrades": DEFAULT_THRESHOLDS.min_trades,
            "minWinRate": DEFAULT_THRESHOLDS.min_win_rate_pct,
            "minNetReturn": DEFAULT_THRESHOLDS.min_net_return_pct,
            "maxDrawdown": DEFAULT_THRESHOLDS.max_drawdown_pct,
        },
        "GUIDELINE_POLICY_OVERRIDES": {
            f"{sym}|{ver}": {
                "advisoryOnly": sorted(list(override.waived_hard_checks)),
            }
            for (sym, ver), override in POLICY_OVERRIDES.items()
        },
    }


if __name__ == "__main__":
    import json

    config = to_js_config()
    print(json.dumps(config, indent=2))
