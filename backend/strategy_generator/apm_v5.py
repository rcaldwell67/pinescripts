from __future__ import annotations

from typing import Any

from apm_v1 import apm_v1_latest_bar_analysis, apm_v1_latest_bar_exit_analysis, apm_v1_signals
from v5_params import get_v5_params


def apm_v5_signals(df, side: str = "short", params: dict[str, Any] | None = None):
    cfg = params or get_v5_params()
    signal = cfg.get("signal", {})
    if side == "long" and not bool(signal.get("enable_longs", False)):
        return []
    if side == "short" and not bool(signal.get("enable_shorts", True)):
        return []
    return apm_v1_signals(df, side=side, params=cfg)


def apm_v5_latest_bar_analysis(df, side: str = "short", params: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = params or get_v5_params()
    signal = cfg.get("signal", {})
    if side == "long" and not bool(signal.get("enable_longs", False)):
        return {
            "is_entry": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "disabled",
            "detail": "long side disabled in v5 params",
            "latest_bar_ts": None,
        }
    if side == "short" and not bool(signal.get("enable_shorts", True)):
        return {
            "is_entry": False,
            "is_near_miss": False,
            "passed_stage": "start",
            "failed_stage": "disabled",
            "detail": "short side disabled in v5 params",
            "latest_bar_ts": None,
        }
    return apm_v1_latest_bar_analysis(df, side=side, params=cfg)


def apm_v5_latest_bar_exit_analysis(df, side: str = "short", params: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = params or get_v5_params()
    return apm_v1_latest_bar_exit_analysis(df, side=side, params=cfg)
