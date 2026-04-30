import pandas as pd

# Example: Simple strategy evaluation
# Guidelines: Win Rate >= 65%, Net Return >= 15%, Max Drawdown <= 4.5%
def evaluate_strategy(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {'win_rate': 0, 'net_return': 0, 'max_drawdown': 0, 'meets_guidelines': False}
    wins = trades[trades['pnl'] > 0]
    win_rate = len(wins) / len(trades)
    net_return = trades['pnl'].sum() / trades['entry_price'].sum()
    # Max drawdown calculation
    cumulative = trades['pnl'].cumsum()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max).min()
    max_drawdown = abs(drawdown) / (running_max.max() if running_max.max() != 0 else 1)
    meets_guidelines = (
        win_rate >= 0.65 and
        net_return >= 0.15 and
        max_drawdown <= 0.045
    )
    return {
        'win_rate': round(win_rate, 4),
        'net_return': round(net_return, 4),
        'max_drawdown': round(max_drawdown, 4),
        'meets_guidelines': meets_guidelines
    }

# Placeholder for strategy logic
# Extend with actual strategy rules and signals
