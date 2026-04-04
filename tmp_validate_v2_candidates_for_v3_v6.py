import json
import sys
from pathlib import Path

sys.path.insert(0, 'backend')
sys.path.insert(0, 'backend/strategy_generator')

from backtest_backtrader_alpaca import fetch_ohlcv
from tune_v3_v6_profile import apply_candidate, evaluate
from v3_params import get_v3_params
from v4_params import get_v4_params
from v5_params import get_v5_params
from v6_params import get_v6_params

symbols = ['BTC/USD', 'CLM', 'CRF', 'ETH/USD', 'BTC/USDC', 'BTC/USDT']
versions = {'v3': get_v3_params, 'v4': get_v4_params, 'v5': get_v5_params, 'v6': get_v6_params}

result_metric_keys = {
    'trades',
    'win_rate',
    'net_return_pct',
    'max_drawdown_pct',
    'pass_win_rate',
    'pass_net_return',
    'pass_drawdown',
    'pass_all',
}

signal_keys = {
    'enable_longs', 'enable_shorts', 'pullback_tolerance_pct', 'momentum_bars',
    'rsi_long_min', 'rsi_long_max', 'rsi_short_min', 'rsi_short_max',
    'adx_slope_bars', 'adx_threshold', 'di_spread', 'session_filter_enabled',
    'session_start_hour_et', 'session_end_hour_et', 'volume_mult_min',
    'min_body_atr_mult', 'atr_floor_pct', 'panic_suppression_mult',
}

risk_keys = {
    'sl_atr_mult', 'tp_atr_mult', 'trail_activate_atr_mult',
    'trail_dist_atr_mult', 'risk_pct', 'max_bars_in_trade',
}

results = {}
for symbol in symbols:
    safe_symbol = ''.join(ch for ch in symbol.lower() if ch.isalnum())
    path = Path('docs/data') / f'v2_profile_tuning_result_{safe_symbol}_guideline.json'
    if not path.exists():
        results[symbol] = {'error': 'missing_v2_candidate'}
        continue

    payload = json.loads(path.read_text(encoding='utf-8'))
    best_candidate = payload.get('best_candidate', {})

    mapped = {}
    for key, value in best_candidate.items():
        if key in result_metric_keys:
            continue
        if key in signal_keys:
            mapped[f'signal.{key}'] = value
        elif key in risk_keys:
            mapped[f'risk.{key}'] = value

    df = fetch_ohlcv(symbol)
    results[symbol] = {}
    for version, loader in versions.items():
        extra = {}
        if version in {'v4', 'v5', 'v6'}:
            extra = {
                'signal.bb_filter_enabled': False,
                'signal.donchian_filter_enabled': False,
            }
        elif version == 'v3':
            extra = {
                'signal.rvol_filter_enabled': False,
                'signal.atr_percentile_filter_enabled': False,
            }

        params = apply_candidate(loader(symbol=symbol), {**mapped, **extra})
        outcome = evaluate(df, version, params, symbol)
        results[symbol][version] = {
            'trades': outcome.trades,
            'win_rate': round(outcome.win_rate, 4),
            'net_return_pct': round(outcome.net_return_pct, 4),
            'max_drawdown_pct': round(outcome.max_drawdown_pct, 4),
            'pass_all': outcome.win_rate >= 70.0 and outcome.net_return_pct >= 20.0 and outcome.max_drawdown_pct <= 4.5,
        }

print(json.dumps(results, indent=2))
