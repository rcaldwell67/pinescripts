import React, { useState } from 'react';
import { runBacktest } from '../api';

export default function BacktestRunner() {
  const [symbol, setSymbol] = useState('');
  const [version, setVersion] = useState('v1');
  const [timespan, setTimespan] = useState('YTD');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleRun = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await runBacktest({ symbol, version, timespan });
      setResult(res);
    } catch (e) {
      setError('Backtest failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: '2rem auto', padding: 24, border: '1px solid #eee', borderRadius: 8 }}>
      <h2>Backtest Runner</h2>
      <div style={{ marginBottom: 16 }}>
        <label>Symbol:&nbsp;
          <input value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="e.g. AAPL or BTC/USD" />
        </label>
      </div>
      <div style={{ marginBottom: 16 }}>
        <label>Strategy Version:&nbsp;
          <select value={version} onChange={e => setVersion(e.target.value)}>
            <option value="v1">APM v1.0-5m</option>
            <option value="v2">APM v2.0-10m</option>
            <option value="v3">APM v3.0</option>
            <option value="v4">APM v4.0</option>
            <option value="v5">APM v5.0</option>
            <option value="v6">APM v6.0</option>
            <option value="v7">APM v7.0</option>
            <option value="universal">APM Universal</option>
            <option value="meanrev_tf">Mean Reversion TrendFilter v1</option>
          </select>
        </label>
      </div>
      <div style={{ marginBottom: 16 }}>
        <label>Timespan:&nbsp;
          <select value={timespan} onChange={e => setTimespan(e.target.value)}>
            <option value="YTD">Year-to-Date</option>
            <option value="MTD">Month-to-Date</option>
            <option value="WTD">Week-to-Date</option>
            <option value="1D">1 Day</option>
            <option value="4H">4 Hours</option>
            <option value="1H">1 Hour</option>
            <option value="30m">30 Minutes</option>
            <option value="15m">15 Minutes</option>
          </select>
        </label>
      </div>
      <button onClick={handleRun} disabled={!symbol || loading}>
        {loading ? 'Running...' : 'Run Backtest'}
      </button>
      {error && <div style={{ color: 'red', marginTop: 12 }}>{error}</div>}
      {result && (
        <div style={{ marginTop: 24 }}>
          <h4>Backtest Metrics</h4>
          <pre style={{ background: '#f8f8f8', padding: 12, borderRadius: 4 }}>
            {JSON.stringify(result.metrics, null, 2)}
          </pre>
          <h4>Trades</h4>
          <div style={{ maxHeight: 200, overflow: 'auto', background: '#fafbfc', border: '1px solid #eee', borderRadius: 4, padding: 8 }}>
            <table style={{ width: '100%', fontSize: '0.95em' }}>
              <thead>
                <tr>
                  <th>Entry</th><th>Exit</th><th>Side</th><th>Entry Price</th><th>Exit Price</th><th>PnL</th>
                </tr>
              </thead>
              <tbody>
                {result.trades && result.trades.map((t, i) => (
                  <tr key={i}>
                    <td>{t.entry_time || t.entry_idx}</td>
                    <td>{t.exit_time || t.exit_idx}</td>
                    <td>{t.direction}</td>
                    <td>{t.entry_price}</td>
                    <td>{t.exit_price}</td>
                    <td>{t.pnl || t.dollar_pnl}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
