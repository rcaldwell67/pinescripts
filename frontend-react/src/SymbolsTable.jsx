import React, { useEffect, useState } from "react";

export default function SymbolsTable() {
  const [symbols, setSymbols] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchSymbols() {
      try {
        const res = await fetch("/pinescripts/data/dashboard_snapshot.json");
        if (!res.ok) throw new Error("Failed to load dashboard_snapshot.json");
        const data = await res.json();
        setSymbols(data.symbols || []);
      } catch (err) {
        setError(err.message || "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    fetchSymbols();
  }, []);

  if (loading) return <section style={{ padding: 24 }}>Loading symbols...</section>;
  if (error) return <section style={{ padding: 24, color: 'red' }}>Error: {error}</section>;

  return (
    <section style={{ padding: 24 }}>
      <h2>Symbols Table</h2>
      <div style={{overflowX: 'auto'}}>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
          <thead>
            <tr style={{background: 'var(--bg-mid)'}}>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Symbol</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Description</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Asset Type</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Live Enabled</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Is Active</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map(sym => (
              <tr key={sym.symbol_key || sym.symbol}>
                <td style={{padding: '8px 12px'}}>{sym.symbol}</td>
                <td style={{padding: '8px 12px'}}>{sym.description || '-'}</td>
                <td style={{padding: '8px 12px'}}>{sym.asset_type || sym.asset_class || '-'}</td>
                <td style={{padding: '8px 12px'}}>{sym.live_enabled !== undefined ? String(sym.live_enabled) : '-'}</td>
                <td style={{padding: '8px 12px'}}>{sym.isactive !== undefined ? String(sym.isactive) : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
