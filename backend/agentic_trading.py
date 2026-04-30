# --- AdaptiveTuner: agentic parameter search with guideline enforcement ---
import random

class AdaptiveTuner:
    """
    Iteratively proposes and evaluates parameter sets, enforcing guidelines and optimizing a target metric.
    Example search: random, grid, or Bayesian (stubbed as random for now).
    """
    def __init__(self, guideline_filter: GuidelineFilter, param_space: Dict[str, list], eval_fn, rank_by: str = None, max_iters: int = 100):
        self.guideline_filter = guideline_filter
        self.param_space = param_space
        self.eval_fn = eval_fn  # Function: params -> result dict
        self.rank_by = rank_by
        self.max_iters = max_iters

    def random_param_set(self) -> Dict[str, Any]:
        return {k: random.choice(v) for k, v in self.param_space.items()}

    def tune(self) -> List[Dict[str, Any]]:
        candidates = []
        for _ in range(self.max_iters):
            params = self.random_param_set()
            result = self.eval_fn(params)
            if result:
                result = {**params, **result}
                candidates.append(result)
        valid = self.guideline_filter.filter(candidates)
        if self.rank_by and valid:
            valid = sorted(valid, key=lambda x: x.get(self.rank_by, 0), reverse=True)
        return valid

# Example usage:
# def evaluate(params):
#     ... # run backtest, return dict with win_rate, net_return, max_drawdown, calmar_ratio, etc.
# filter = GuidelineFilter(symbol="BTCUSD", version="v7")
# tuner = AdaptiveTuner(filter, param_space, evaluate, rank_by="calmar_ratio", max_iters=100)
# best = tuner.tune()
"""
Agentic Trading module: integrates Trading Strategy Guidelines into agentic selection, tuning, and execution.
"""
from .config.guideline_policy import evaluate_backtest_guideline
from typing import List, Dict, Any

class GuidelineFilter:
    """Filters candidate strategies/parameter sets by Trading Strategy Guidelines."""
    def __init__(self, symbol: str, version: str):
        self.symbol = symbol
        self.version = version

    def filter(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return only candidates that pass all guidelines."""
        passing = []
        for c in candidates:
            trades = c.get("trades")
            win_rate = c.get("win_rate")
            net_return = c.get("net_return")
            max_drawdown = c.get("max_drawdown")
            passed, _ = evaluate_backtest_guideline(
                self.symbol, self.version, trades, win_rate, net_return, max_drawdown
            )
            if passed:
                passing.append(c)
        return passing

class AgenticStrategySelector:
    """Selects valid strategies using GuidelineFilter, can rank by additional metrics."""
    def __init__(self, guideline_filter: GuidelineFilter):
        self.guideline_filter = guideline_filter

    def select(self, candidates: List[Dict[str, Any]], rank_by: str = None) -> List[Dict[str, Any]]:
        valid = self.guideline_filter.filter(candidates)
        if rank_by and valid:
            valid = sorted(valid, key=lambda x: x.get(rank_by, 0), reverse=True)
        return valid

# Example usage:
# filter = GuidelineFilter(symbol="BTCUSD", version="v7")
# selector = AgenticStrategySelector(filter)
# valid_strategies = selector.select(candidate_list, rank_by="calmar_ratio")
