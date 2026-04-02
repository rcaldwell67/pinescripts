from __future__ import annotations

from typing import Any

from apm_v1 import apm_v1_latest_bar_analysis, apm_v1_latest_bar_exit_analysis, apm_v1_signals
from v6_params import get_v6_params


def apm_v6_signals(df, side: str = "short", params: dict[str, Any] | None = None):
    cfg = params or get_v6_params()
    signal = cfg.get("signal", {})
    if side == "long" and not bool(signal.get("enable_longs", False)):
        return []
    if side == "short" and not bool(signal.get("enable_shorts", True)):
        return []
    return apm_v1_signals(df, side=side, params=cfg)


def apm_v6_latest_bar_analysis(df, side: str = "short", params: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = params or get_v6_params()
    signal = cfg.get("signal", {})
    if side == "long" and not bool(signal.get("enable_longs", False)):
        return {
            "is_entry": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "disabled",
            "detail": "long side disabled in v6 params",
            "latest_bar_ts": None,
        }
    if side == "short" and not bool(signal.get("enable_shorts", True)):
        return {
            "is_entry": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "disabled",
            "detail": "short side disabled in v6 params",
            "latest_bar_ts": None,
        }
    return apm_v1_latest_bar_analysis(df, side=side, params=cfg)


def apm_v6_latest_bar_exit_analysis(df, side: str = "short", params: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = params or get_v6_params()
    return apm_v1_latest_bar_exit_analysis(df, side=side, params=cfg)
