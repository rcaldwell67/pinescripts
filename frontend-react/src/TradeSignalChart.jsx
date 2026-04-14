import React, { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, Scatter, ScatterChart } from "recharts";

// Example usage: <TradeSignalChart symbol="BTC/USD" />
export default function TradeSignalChart({ symbol }) {
  const [data, setData] = useState([]);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchData() {
      try {
        // Replace with your actual API or data source
        const priceRes = await fetch(`/pinescripts/data/${symbol.replace('/', '')}_ohlcv.json`);
        const tradesRes = await fetch(`/pinescripts/data/${symbol.replace('/', '')}_trades.json`);
        if (!priceRes.ok || !tradesRes.ok) throw new Error("Failed to load data");
        const priceData = await priceRes.json();
        const tradeData = await tradesRes.json();
        setData(priceData);
        setTrades(tradeData);
      } catch (err) {
        setError(err.message || "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [symbol]);

  if (loading) return <div>Loading trade signal chart...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;
  if (!data.length) return <div>No price data available.</div>;

  // Map trades to chart points
  const buySignals = trades.filter(t => t.side === 'buy').map(t => ({ x: t.timestamp, y: t.price }));
  const sellSignals = trades.filter(t => t.side === 'sell').map(t => ({ x: t.timestamp, y: t.price }));

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={data} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
        <XAxis dataKey="timestamp" tickFormatter={ts => ts.slice(5, 16)} minTickGap={40} />
        <YAxis domain={['auto', 'auto']} />
        <Tooltip />
        <Legend />
        <Line type="monotone" dataKey="close" stroke="#8884d8" dot={false} name="Close Price" />
        <Scatter data={buySignals} fill="#4caf50" name="Buy Signal" shape="triangle" />
        <Scatter data={sellSignals} fill="#f44336" name="Sell Signal" shape="cross" />
      </LineChart>
    </ResponsiveContainer>
  );
}
