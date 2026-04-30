import React, { useEffect, useState } from 'react';
import { getSymbols, runBacktest, evaluateStrategy } from '../api';

const STRATEGY_VERSIONS = [
  { value: 'v1', label: 'APM v1.0-5m' },
  { value: 'v2', label: 'APM v2.0-10m' },
  { value: 'v3', label: 'APM v3.0' },
  { value: 'v4', label: 'APM v4.0' },
  { value: 'v5', label: 'APM v5.0' },
  { value: 'v6', label: 'APM v6.0' },
  { value: 'v7', label: 'APM v7.0' },
  { value: 'universal', label: 'APM Universal' },
  { value: 'meanrev_tf', label: 'Mean Reversion TrendFilter v1' },
];

export default function StrategyManager() {
  const [symbols, setSymbols] = useState([]);
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [selectedVersion, setSelectedVersion] = useState('v1');
  const [backtestResult, setBacktestResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    getSymbols().then(setSymbols).catch(() => setSymbols([]));
  }, []);

  const handleBacktest = async () => {
    setLoading(true);
    setError('');
    setBacktestResult(null);
    try {
      const result = await runBacktest({ symbol: selectedSymbol, version: selectedVersion });
      setBacktestResult(result);
    } catch (e) {
      setError('Backtest failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: '2rem auto', padding: 24, border: '1px solid #eee', borderRadius: 8 }}>
      <h2>Strategy Management</h2>
      <div style={{ marginBottom: 16 }}>
        <label>Symbol:&nbsp;
          <select value={selectedSymbol} onChange={e => setSelectedSymbol(e.target.value)}>
            <option value="">Select symbol</option>
            {symbols.map(s => (
              <option key={s.symbol} value={s.symbol}>{s.symbol}</option>
            ))}
          </select>
        </label>
      </div>
      <div style={{ marginBottom: 16 }}>
        <label>Strategy Version:&nbsp;
          <select value={selectedVersion} onChange={e => setSelectedVersion(e.target.value)}>
            {STRATEGY_VERSIONS.map(v => (
              <option key={v.value} value={v.value}>{v.label}</option>
            ))}
          </select>
        </label>
      </div>
      <button onClick={handleBacktest} disabled={!selectedSymbol || loading}>
        {loading ? 'Running...' : 'Run Backtest'}
      </button>
      {error && <div style={{ color: 'red', marginTop: 12 }}>{error}</div>}
      {backtestResult && (
        <div style={{ marginTop: 24 }}>
          <h4>Backtest Result</h4>
          <pre style={{ background: '#f8f8f8', padding: 12, borderRadius: 4 }}>
            {JSON.stringify(backtestResult.metrics, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
