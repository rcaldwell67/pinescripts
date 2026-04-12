import React, { useEffect, useState } from "react";

export default function BacktestsTable() {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/pinescripts/data/dashboard_snapshot.json")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load dashboard_snapshot.json");
        return res.json();
      })
      .then((data) => {
        setSnapshot(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <section style={{ padding: 24 }}>Loading backtest data...</section>;
  if (error) return <section style={{ padding: 24, color: 'red' }}>Error: {error}</section>;
  if (!snapshot) return null;

  return (
    <section style={{ padding: 24 }}>
      <h2>Backtests (v6) - Active Symbols</h2>
      <div style={{overflowX: 'auto'}}>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
          <thead>
            <tr style={{background: 'var(--bg-mid)'}}>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Symbol</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Current Equity</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Net Return %</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Win Rate</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Total Trades</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Last Updated</th>
            </tr>
          </thead>
          <tbody>
            {snapshot.symbols.map(sym => {
              const result = snapshot.results.backtest.find(r => r.symbol_key === sym.symbol_key);
              return (
                <tr key={sym.symbol_key}>
                  <td style={{padding: '8px 12px'}}>{sym.symbol}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.current_equity ?? '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.net_return_pct != null ? result.net_return_pct.toFixed(2) + '%' : '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.win_rate != null ? result.win_rate.toFixed(1) + '%' : '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.total_trades ?? '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.timestamp ?? '-'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}