import React, { useEffect, useState } from "react";

export default function SimulatedPaperTable() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadData() {
      try {
        // Fetch from backend API endpoint (to be implemented)
        const res = await fetch("http://localhost:4000/api/paper-trading-results");
        if (!res.ok) throw new Error("Failed to load paper trading results from API");
        let json;
        try {
          json = await res.json();
        } catch (jsonErr) {
          throw new Error("Invalid JSON from paper trading results API");
        }
        setData(json);
      } catch (err) {
        setError(err.message || "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) return <div>Loading simulated paper trading data...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;
  if (!data) return null;

  // Only show rows for v6, and only if there is at least one row
  const v6Rows = Object.entries(data).flatMap(([symbol, results]) =>
    results.filter(row => row.version === 'v6').map((row, i) => ({ symbol, ...row }))
  );
  if (v6Rows.length === 0) return <div>No simulated paper trading data available.</div>;

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
          {v6Rows.map((row, i) => (
            <tr key={row.symbol + row.version}>
              <td>{row.symbol}</td>
              <td>{row.version}</td>
              <td>{row.net_return_pct != null ? row.net_return_pct.toFixed(2) + '%' : '-'}</td>
              <td>{row.win_rate != null ? row.win_rate.toFixed(1) + '%' : '-'}</td>
              <td>{row.total_trades ?? '-'}</td>
              <td>{row.max_drawdown != null ? row.max_drawdown.toFixed(2) + '%' : '-'}</td>
              <td>{row.first_trade_date ?? '-'}</td>
              <td>{row.last_trade_date ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
