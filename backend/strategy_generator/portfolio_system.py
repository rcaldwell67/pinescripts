from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PortfolioDecision:
    allow_trade: bool
    reason: str
    risk_multiplier: float
    regime_score: int


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _latest(df, column: str, default: float = 0.0) -> float:
    try:
        if column not in df.columns:
            return default
        return _safe_float(df[column].iloc[-1], default)
    except Exception:
        return default


def evaluate_trade(
    symbol: str,
    side: str,
    df,
    *,
    portfolio_cfg: dict[str, Any] | None = None,
    min_adx: float = 14.0,
    min_volume_ratio: float = 0.35,
    min_atr_pct: float = 0.08,
) -> PortfolioDecision:
    """Portfolio-level trade gate and risk scaling.

    This sits above strategy entry logic and enforces a simple regime quality
    check before order submission. It returns both allow/deny and a risk
    multiplier so weak-but-acceptable regimes can trade smaller size.
    """
    cfg = portfolio_cfg or {}
    min_adx = _safe_float(cfg.get("min_adx"), min_adx)
    min_volume_ratio = _safe_float(cfg.get("min_volume_ratio"), min_volume_ratio)
    min_atr_pct = _safe_float(cfg.get("min_atr_pct"), min_atr_pct)
    weak_regime_min_score = int(_safe_float(cfg.get("weak_regime_min_score"), 3.0))
    weak_regime_risk_multiplier = _safe_float(cfg.get("weak_regime_risk_multiplier"), 0.75)
    strong_regime_risk_multiplier = _safe_float(cfg.get("strong_regime_risk_multiplier"), 1.0)
    crypto_risk_multiplier = _safe_float(cfg.get("crypto_risk_multiplier"), 0.9)

    if df is None or len(df) < 210:
        return PortfolioDecision(False, "insufficient_history", 0.0, 0)

    close = _latest(df, "Close")
    ema21 = _latest(df, "ema21")
    ema50 = _latest(df, "ema50")
    ema200 = _latest(df, "ema200")
    adx = _latest(df, "adx")
    atr = _latest(df, "atr")
    volume = _latest(df, "Volume")
    vol_sma = _latest(df, "vol_sma")

    if close <= 0:
        return PortfolioDecision(False, "invalid_price", 0.0, 0)

    if side == "long":
        stack_ok = ema21 > ema50 > ema200
    else:
        stack_ok = ema21 < ema50 < ema200

    adx_ok = adx >= min_adx
    atr_pct = (atr / close) * 100.0 if atr > 0 else 0.0
    volatility_ok = atr_pct >= min_atr_pct
    vol_ratio = (volume / vol_sma) if vol_sma > 0 else 0.0
    liquidity_ok = vol_ratio >= min_volume_ratio

    checks = [stack_ok, adx_ok, volatility_ok, liquidity_ok]
    score = sum(1 for v in checks if v)

    if not stack_ok:
        return PortfolioDecision(False, "regime_stack_mismatch", 0.0, score)
    if score < weak_regime_min_score:
        return PortfolioDecision(False, "weak_regime", 0.0, score)

    # Scale down risk for acceptable-but-not-perfect regimes.
    risk_multiplier = strong_regime_risk_multiplier if score == 4 else weak_regime_risk_multiplier

    # Slightly reduce crypto exposure to limit correlation/volatility bursts.
    if "/" in symbol:
        risk_multiplier *= crypto_risk_multiplier

    return PortfolioDecision(True, "ok", risk_multiplier, score)
