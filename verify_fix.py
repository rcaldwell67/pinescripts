import sys
sys.path.insert(0, r'd:\OneDrive\codebase\pinescripts-1\backend')
sys.path.insert(0, r'd:\OneDrive\codebase\pinescripts-1\backend\strategy_generator')
from backtest_backtrader_alpaca import fetch_ohlcv, run_backtest

VERSIONS = ('v1', 'v2', 'v3', 'v4', 'v5', 'v6')

for sym in ['BTC/USD', 'ETH/USD', 'CLM', 'CRF']:
    print(f"Fetching {sym}...")
    df = fetch_ohlcv(sym)
    for version in VERSIONS:
        trades = run_backtest(df, version, symbol=sym)
        total_pnl = trades['pnl'].sum() if len(trades) else 0
        win_rate = (trades['pnl'] > 0).mean() * 100 if len(trades) else 0
        net_ret = (trades['equity'].iloc[-1] / (trades['equity'].iloc[0] - trades['pnl'].iloc[0]) - 1) * 100 if len(trades) else 0
        print(f"  {sym} {version}: {len(trades)} trades, pnl=${total_pnl:.0f}, win={win_rate:.1f}%, net_ret={net_ret:.1f}%")
