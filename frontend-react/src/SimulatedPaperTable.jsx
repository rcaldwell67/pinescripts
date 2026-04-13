import React, { useEffect, useState } from "react";

export default function SimulatedPaperTable() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/pinescripts/data/paper_trading_results.json")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load paper_trading_results.json");
        return res.json();
      })
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div>Loading simulated paper trading data...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;
  if (!data) return null;

  return (
    <div style={{overflowX: 'auto'}}>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
        <thead>
          <tr style={{background: 'var(--bg-mid)'}}>
            <th>Symbol</th>
            <th>Version</th>
            <th>Net Return %</th>
            <th>Win Rate</th>
            <th>Total Trades</th>
            <th>Max Drawdown</th>
            <th>First Trade</th>
            <th>Last Trade</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).flatMap(([symbol, results]) =>
            results.filter(row => row.version === 'v6').map((row, i) => (
              <tr key={symbol + row.version}>
                <td>{symbol}</td>
                <td>{row.version}</td>
                <td>{row.net_return_pct != null ? row.net_return_pct.toFixed(2) + '%' : '-'}</td>
                <td>{row.win_rate != null ? row.win_rate.toFixed(1) + '%' : '-'}</td>
                <td>{row.total_trades ?? '-'}</td>
                <td>{row.max_drawdown != null ? row.max_drawdown.toFixed(2) + '%' : '-'}</td>
                <td>{row.first_trade_date ?? '-'}</td>
                <td>{row.last_trade_date ?? '-'}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
