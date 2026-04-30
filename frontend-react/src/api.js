// API service layer for backend integration
const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:5000/api';

export async function getSymbols() {
  const res = await fetch(`${API_BASE}/symbols`);
  return res.json();
}

export async function getYFinanceBars(symbol, start, end, interval = '1d') {
  const url = `${API_BASE}/yfinance-bars?symbol=${symbol}&start=${start}&end=${end}&interval=${interval}`;
  const res = await fetch(url);
  return res.json();
}

export async function getNewsSentiment(symbol) {
  const url = `${API_BASE}/news-sentiment?symbol=${symbol}`;
  const res = await fetch(url);
  return res.json();
}

export async function evaluateStrategy(trades) {
  const res = await fetch(`${API_BASE}/strategy/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trades })
  });
  return res.json();
}

export async function runBacktest({ symbol, version, timespan, profile, params }) {
  const res = await fetch(`${API_BASE}/backtest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, version, timespan, profile, params })
  });
  return res.json();
}

export async function placeLiveTrade({ symbol, qty, side }) {
  const res = await fetch(`${API_BASE}/live-trade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, qty, side })
  });
  return res.json();
}

export async function getLivePositions() {
  const res = await fetch(`${API_BASE}/live-positions`);
  return res.json();
}

export async function getLiveOrders() {
  const res = await fetch(`${API_BASE}/live-orders`);
  return res.json();
}
