"""Backtesting engine for Adaptive Pullback Momentum v2.0-10m."""

from __future__ import annotations

import pandas as pd

from apm_v2 import apm_v2_signals
from v2_params import get_v2_params


def backtest_apm_v2(df, params=None):
    params = params or get_v2_params()
    risk = params["risk"]
    signal = params.get("signal", {})

    long_entries = set(apm_v2_signals(df, side="long", params=params)) if signal.get("enable_longs", False) else set()
    short_entries = set(apm_v2_signals(df, side="short", params=params)) if signal.get("enable_shorts", True) else set()

    equity = float(risk["initial_equity"])
    trades = []
    open_until = -1
    sl_mult = float(risk["sl_atr_mult"])
    tp_mult = float(risk["tp_atr_mult"])
    trail_activate_mult = float(risk["trail_activate_atr_mult"])
    trail_dist_mult = float(risk["trail_dist_atr_mult"])
    max_bars = int(risk["max_bars_in_trade"])

    # Drawdown-aware circuit breaker parameters
    max_dd_percent = 4.5
    max_equity = equity
    circuit_breaker = False

    for i in range(len(df)):
        if i <= open_until:
            continue

        # Update equity peak and drawdown
        max_equity = max(max_equity, equity)
        current_dd = ((max_equity - equity) / max_equity) * 100 if max_equity > 0 else 0
        # Drawdown ladder for risk adjustment
        if current_dd < 1.5:
            risk_pct = 0.5
        elif current_dd < 3.0:
            risk_pct = 0.25
        elif current_dd < 4.0:
            risk_pct = 0.1
        else:
            risk_pct = 0.0
        # Circuit breaker: halt trading if drawdown exceeds max
        if current_dd >= max_dd_percent:
            circuit_breaker = True
        if circuit_breaker:
            break

        if i in long_entries:
            side = "long"
        elif i in short_entries:
            side = "short"
        else:
            continue

        entry_price = float(df["Close"].iloc[i])
        atr = float(df["atr"].iloc[i])
        if pd.isna(atr) or atr <= 0:
            continue

        if side == "long":
            sl = entry_price - sl_mult * atr
            tp = entry_price + tp_mult * atr
            risk_per_unit = entry_price - sl
        else:
            sl = entry_price + sl_mult * atr
            tp = entry_price - tp_mult * atr
            risk_per_unit = sl - entry_price

        if risk_per_unit <= 0 or risk_pct == 0.0:
            continue

        qty = equity * risk_pct / 100.0 / risk_per_unit
        trail_active = False
        best_price = entry_price
        exit_price = None
        exit_type = None

        trade_end = len(df) if max_bars <= 0 else min(i + max_bars, len(df))
        for j in range(i + 1, trade_end):
            price = float(df["Close"].iloc[j])

            if side == "long":
                if not trail_active and price > entry_price + trail_activate_mult * atr:
                    trail_active = True
                    best_price = price
                if trail_active:
                    best_price = max(best_price, price)
                    trail_stop = best_price - trail_dist_mult * atr
                    if price < trail_stop:
                        exit_price = trail_stop
                        exit_type = "trailing_stop"
                        break
                if price <= sl:
                    exit_price = sl
                    exit_type = "stop_loss"
                    break
                if price >= tp:
                    exit_price = tp
                    exit_type = "take_profit"
                    break
            else:
                if not trail_active and price < entry_price - trail_activate_mult * atr:
                    trail_active = True
                    best_price = price
                if trail_active:
                    best_price = min(best_price, price)
                    trail_stop = best_price + trail_dist_mult * atr
                    if price > trail_stop:
                        exit_price = trail_stop
                        exit_type = "trailing_stop"
                        break
                if price >= sl:
                    exit_price = sl
                    exit_type = "stop_loss"
                    break
                if price <= tp:
                    exit_price = tp
                    exit_type = "take_profit"
                    break

        if exit_price is None:
            j = min(trade_end - 1, len(df) - 1)
            exit_price = float(df["Close"].iloc[j])
            exit_type = "max_bars_exit"

        open_until = j
        pnl = (exit_price - entry_price) * qty if side == "long" else (entry_price - exit_price) * qty
        equity += pnl
        trades.append(
            {
                "entry_idx": i,
                "exit_idx": j,
                "side": side,
                "entry": entry_price,
                "exit": exit_price,
                "qty": qty,
                "pnl": pnl,
                "exit_type": exit_type,
                "equity": equity,
                "drawdown": current_dd,
                "risk_pct": risk_pct,
            }
        )

    return pd.DataFrame(trades)
