import React, { useState } from 'react';
import { placeLiveTrade, getLivePositions, getLiveOrders } from '../api';

export default function LiveTradingPanel() {
  const [symbol, setSymbol] = useState('');
  const [qty, setQty] = useState(1);
  const [side, setSide] = useState('buy');
  const [orderResult, setOrderResult] = useState(null);
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleTrade = async () => {
    setLoading(true);
    setError('');
    setOrderResult(null);
    try {
      const res = await placeLiveTrade({ symbol, qty, side });
      setOrderResult(res);
      fetchPositions();
      fetchOrders();
    } catch (e) {
      setError('Trade failed.');
    } finally {
      setLoading(false);
    }
  };

  const fetchPositions = async () => {
    try {
      const res = await getLivePositions();
      setPositions(res.positions || []);
    } catch {}
  };

  const fetchOrders = async () => {
    try {
      const res = await getLiveOrders();
      setOrders(res.orders || []);
    } catch {}
  };

  return (
    <div style={{ maxWidth: 600, margin: '2rem auto', padding: 24, border: '1px solid #eee', borderRadius: 8 }}>
      <h2>Live Trading Control</h2>
      <div style={{ marginBottom: 16 }}>
        <label>Symbol:&nbsp;
          <input value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="e.g. AAPL or BTC/USD" />
        </label>
      </div>
      <div style={{ marginBottom: 16 }}>
        <label>Quantity:&nbsp;
          <input type="number" value={qty} min={1} onChange={e => setQty(Number(e.target.value))} />
        </label>
      </div>
      <div style={{ marginBottom: 16 }}>
        <label>Side:&nbsp;
          <select value={side} onChange={e => setSide(e.target.value)}>
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
        </label>
      </div>
      <button onClick={handleTrade} disabled={!symbol || !qty || loading}>
        {loading ? 'Placing...' : 'Place Trade'}
      </button>
      {error && <div style={{ color: 'red', marginTop: 12 }}>{error}</div>}
      {orderResult && (
        <div style={{ marginTop: 24 }}>
          <h4>Order Result</h4>
          <pre style={{ background: '#f8f8f8', padding: 12, borderRadius: 4 }}>
            {JSON.stringify(orderResult, null, 2)}
          </pre>
        </div>
      )}
      <div style={{ marginTop: 32 }}>
        <button onClick={fetchPositions} style={{ marginRight: 8 }}>Refresh Positions</button>
        <button onClick={fetchOrders}>Refresh Orders</button>
      </div>
      <div style={{ marginTop: 24 }}>
        <h4>Current Positions</h4>
        <div style={{ maxHeight: 120, overflow: 'auto', background: '#fafbfc', border: '1px solid #eee', borderRadius: 4, padding: 8 }}>
          <table style={{ width: '100%', fontSize: '0.95em' }}>
            <thead>
              <tr>
                <th>Symbol</th><th>Qty</th><th>Side</th><th>Market Value</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={i}>
                  <td>{p.symbol}</td>
                  <td>{p.qty}</td>
                  <td>{p.side || p.asset_side}</td>
                  <td>{p.market_value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div style={{ marginTop: 24 }}>
        <h4>Recent Orders</h4>
        <div style={{ maxHeight: 120, overflow: 'auto', background: '#fafbfc', border: '1px solid #eee', borderRadius: 4, padding: 8 }}>
          <table style={{ width: '100%', fontSize: '0.95em' }}>
            <thead>
              <tr>
                <th>Symbol</th><th>Qty</th><th>Side</th><th>Status</th><th>Submitted At</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o, i) => (
                <tr key={i}>
                  <td>{o.symbol}</td>
                  <td>{o.qty}</td>
                  <td>{o.side}</td>
                  <td>{o.status}</td>
                  <td>{o.submitted_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
