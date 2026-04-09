// Guideline thresholds (should match backend/config/guideline_policy.py)
const GUIDELINE_THRESHOLDS = {
  minTrades: 10,
  minWinRate: 65.0,
  minNetReturn: 15.0,
  maxDrawdown: 4.5,
};

function guidelineStatus(row) {
  if (!row) return null;
  const fails = [];
  if (row.total_trades < GUIDELINE_THRESHOLDS.minTrades) fails.push("trades");
  if (row.win_rate < GUIDELINE_THRESHOLDS.minWinRate) fails.push("win rate");
  if (row.net_return_pct < GUIDELINE_THRESHOLDS.minNetReturn) fails.push("return");
  if (row.max_drawdown_pct > GUIDELINE_THRESHOLDS.maxDrawdown) fails.push("drawdown");
  return fails.length === 0 ? "PASS" : `FAIL: ${fails.join(", ")}`;
}
import { useEffect, useMemo, useState } from "react";
import TradeGapAnalysis from "./TradeGapAnalysis";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const dataUrl = `${import.meta.env.BASE_URL}data/dashboard_snapshot.json`;

function fmtCurrency(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

function fmtPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return `${n.toFixed(2)}%`;
}

function scoreFromTrade(t) {
  const pnl = Number(t?.dollar_pnl || 0);
  if (pnl > 0) return "win";
  if (pnl < 0) return "loss";
  return "flat";
}

export default function App() {
  const [snapshot, setSnapshot] = useState(null);
  const [symbolFilter, setSymbolFilter] = useState("ALL");
  const [assetFilter, setAssetFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [alpacaSymbols, setAlpacaSymbols] = useState([]);
  const [selectedAlpacaSymbol, setSelectedAlpacaSymbol] = useState("");
  const [alpacaLoading, setAlpacaLoading] = useState(false);
  // Alpaca type filters (checkboxes for crypto, stocks)
  const [typeFilters, setTypeFilters] = useState({ crypto: true, stocks: true });

  // Load Alpaca symbols (simulate API or static list for demo)
  const fetchAlpacaSymbols = async () => {
    setAlpacaLoading(true);
    try {
      const res = await fetch("https://raw.githubusercontent.com/rcaldwell67/pinescripts/main/docs/data/alpaca_symbols.json");
      if (!res.ok) throw new Error("Failed to load Alpaca symbols");
      const data = await res.json();
      setAlpacaSymbols(data.symbols || []);
    } catch (e) {
      setAlpacaSymbols([]);
    } finally {
      setAlpacaLoading(false);
    }
  };
  useEffect(() => {
    fetchAlpacaSymbols();
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(dataUrl, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setSnapshot(json);
      } catch (err) {
        setError(`Failed to load snapshot: ${String(err?.message || err)}`);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const symbols = snapshot?.symbols || [];
  const symbolOptions = ["ALL", ...symbols.map((s) => s.symbol)];

  const filteredTrades = useMemo(() => {
    const trades = (snapshot?.trades || []).filter(t => t.version === 'v6');
    return trades.filter((t) => {
      const symbolOk = symbolFilter === "ALL" || t.symbol === symbolFilter;
      const assetOk = assetFilter === "all" || t.asset_class === assetFilter;
      return symbolOk && assetOk;
    });
  }, [snapshot, symbolFilter, assetFilter]);

  const latestResults = useMemo(() => {
    const results = [];
    const groups = snapshot?.results || {};
    for (const mode of ["backtest", "paper", "live"]) {
      for (const row of (groups[mode] || []).filter(r => r.version === 'v6')) {
        const symbolOk = symbolFilter === "ALL" || row.symbol === symbolFilter;
        const asset = symbols.find((s) => s.symbol === row.symbol)?.asset_class || "etf";
        const assetOk = assetFilter === "all" || asset === assetFilter;
        if (symbolOk && assetOk) {
          results.push({ ...row, asset_class: asset });
        }
      }
    }
    return results;
  }, [snapshot, symbolFilter, assetFilter, symbols]);

  const tradeMix = useMemo(() => {
    let wins = 0;
    let losses = 0;
    let flat = 0;
    for (const t of filteredTrades) {
      const score = scoreFromTrade(t);
      if (score === "win") wins += 1;
      else if (score === "loss") losses += 1;
      else flat += 1;
    }
    return [
      { name: "Wins", value: wins },
      { name: "Losses", value: losses },
      { name: "Flat", value: flat },
    ];
  }, [filteredTrades]);

  const equitySeries = useMemo(() => {
    const rows = filteredTrades
      .filter((t) => Number.isFinite(Number(t.equity)))
      .slice()
      .reverse()
      .map((t, idx) => ({
        i: idx + 1,
        equity: Number(t.equity),
      }));
    return rows;
  }, [filteredTrades]);

  const account = snapshot?.account || {};

  // Handler for Add Symbol button
  function handleAddSymbol() {
    if (!selectedAlpacaSymbol) {
      alert("Please select a symbol from the dropdown first.");
      return;
    }
    const desc = window.prompt("Enter a description for this symbol (optional):", "");
    const title = encodeURIComponent("Add symbol: " + selectedAlpacaSymbol);
    const body = encodeURIComponent(
      `Symbol: ${selectedAlpacaSymbol}\nDescription: ${desc || ""}\n\n_Selected from Alpaca Paper Trading assets via dashboard._`
    );
    const url = `https://github.com/rcaldwell67/pinescripts/issues/new?title=${title}&body=${body}&labels=add-symbol`;
    window.open(url, "_blank");
  }

  // Helper: determine if a symbol matches the selected type filters
  function matchesTypeFilters(sym) {
    const assetClass = (sym.asset_class || '').toLowerCase();
    if (typeFilters.crypto && assetClass === 'crypto') return true;
    if (typeFilters.stocks && (assetClass === 'us_equity' || assetClass === 'etf')) return true;
    return false;
  }
  // Filter Alpaca symbols to only those not already in the dashboard, and by checked types
  const existingSymbols = new Set(symbols.map(s => s.symbol));
  const availableAlpacaSymbols = alpacaSymbols
    .filter(s => !existingSymbols.has(s))
    .filter(matchesTypeFilters);

  // Handler for Remove Symbol button
  function handleRemoveSymbol() {
    if (!symbolFilter || symbolFilter === "ALL") {
      alert("Please select a symbol to remove.");
      return;
    }
    const confirmRemove = window.confirm(`Are you sure you want to request removal of symbol: ${symbolFilter}?`);
    if (!confirmRemove) return;
    const title = encodeURIComponent("Remove symbol: " + symbolFilter);
    const body = encodeURIComponent(`Symbol: ${symbolFilter}\n\n_Request to remove symbol from dashboard via React app._`);
    const url = `https://github.com/rcaldwell67/pinescripts/issues/new?title=${title}&body=${body}&labels=remove-symbol`;
    window.open(url, "_blank");
  }

  return (
    <div className="page-shell">
      <div className="bg-grid" />
      <header className="topbar">
        <div>
          <p className="eyebrow">PulseBoard</p>
          <h1>Crypto + ETF Trading Monitor</h1>
          <p className="sub">Unified backtest, paper, and live observability from Alpaca + Backtrader.</p>
        </div>
        <div className="chip">Snapshot: {snapshot?.generated_at || "-"}</div>
      </header>

      <section className="controls" style={{ alignItems: 'end', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label>Symbol
            <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}>
              {symbolOptions.map((symbol) => (
                <option key={symbol} value={symbol}>{symbol}</option>
              ))}
            </select>
          </label>
          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <button
              type="button"
              style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid var(--edge)', background: 'var(--aqua)', color: '#181c20', fontWeight: 600, cursor: 'pointer' }}
              onClick={fetchAlpacaSymbols}
              title="Refresh available Alpaca symbols"
            >Refresh</button>
            <button
              type="button"
              style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid #f85149', background: '#f85149', color: '#fff', fontWeight: 600, cursor: symbolFilter && symbolFilter !== 'ALL' ? 'pointer' : 'not-allowed', opacity: symbolFilter && symbolFilter !== 'ALL' ? 1 : 0.4 }}
              onClick={handleRemoveSymbol}
              disabled={!symbolFilter || symbolFilter === 'ALL'}
              title="Request removal of selected symbol from dashboard"
            >Remove</button>
          </div>
        </div>
        <label>Asset Class
          <select value={assetFilter} onChange={(e) => setAssetFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="crypto">Crypto</option>
            <option value="etf">ETF</option>
          </select>
        </label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label>Add Alpaca Symbol</label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select
              value={selectedAlpacaSymbol}
              onChange={e => setSelectedAlpacaSymbol(e.target.value)}
              disabled={alpacaLoading || availableAlpacaSymbols.length === 0}
              style={{ minWidth: 120 }}
            >
              <option value="">{alpacaLoading ? "Loading..." : availableAlpacaSymbols.length === 0 ? "No symbols available" : "Select..."}</option>
              {availableAlpacaSymbols.map(sym => (
                <option key={sym} value={sym}>{sym}</option>
              ))}
            </select>
            <button
              type="button"
              style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid var(--edge)', background: 'var(--aqua)', color: '#181c20', fontWeight: 600, cursor: 'pointer' }}
              onClick={handleAddSymbol}
              disabled={!selectedAlpacaSymbol}
            >Add</button>
            <div style={{ display: 'flex', gap: 8, marginLeft: 8 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={typeFilters.crypto}
                  onChange={e => setTypeFilters(f => ({ ...f, crypto: e.target.checked }))}
                /> Crypto
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={typeFilters.stocks}
                  onChange={e => setTypeFilters(f => ({ ...f, stocks: e.target.checked }))}
                /> Stocks
              </label>
            </div>
            {alpacaLoading && <span style={{ color: '#ffa657', fontSize: 13 }}>Loading symbols...</span>}
            {!alpacaLoading && availableAlpacaSymbols.length === 0 && (
              <span style={{ color: '#ffa657', fontSize: 13, marginLeft: 8 }}>
                No symbols available. Check your filters or data source.
              </span>
            )}
          </div>
        </div>
      </section>

      {loading && <div className="panel">Loading snapshot...</div>}
      {error && <div className="panel error">{error}</div>}

      {!loading && !error && (
        <>
          <section className="kpi-grid">
            <article className="kpi">
              <h3>Current Balance</h3>
              <p>{fmtCurrency(account.current_balance)}</p>
            </article>
            <article className="kpi">
              <h3>Buying Power</h3>
              <p>{fmtCurrency(account.buying_power)}</p>
            </article>
            <article className="kpi">
              <h3>Recent Trades</h3>
              <p>{filteredTrades.length}</p>
            </article>
            <article className="kpi">
              <h3>Tracked Symbols</h3>
              <p>{symbols.length}</p>
            </article>
          </section>

          <section className="two-col">
            <article className="panel">
              <h2>Equity Trail</h2>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={equitySeries}>
                    <defs>
                      <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#2ad4ff" stopOpacity={0.55} />
                        <stop offset="95%" stopColor="#2ad4ff" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="4 4" stroke="#274253" />
                    <XAxis dataKey="i" stroke="#9bb4c7" />
                    <YAxis stroke="#9bb4c7" />
                    <Tooltip />
                    <Area type="monotone" dataKey="equity" stroke="#2ad4ff" fill="url(#eqFill)" strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="panel">
              <h2>Trade Outcome Mix</h2>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={tradeMix}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      fill="#5f87ff"
                      label
                    />
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </article>
          </section>

          <section className="panel">
            <h2>Mode Snapshots</h2>
            <table>
              <thead>
                <tr>
                  <th>Mode</th>
                  <th>Symbol</th>
                  <th>Net Return</th>
                  <th>Win Rate</th>
                  <th>Max DD</th>
                  <th>Trades</th>
                </tr>
              </thead>
              <tbody>
                {latestResults.map((row, idx) => (
                  <tr key={`${row.mode}-${row.symbol}-${idx}`}>
                    <td><span className={`badge ${row.mode}`}>{row.mode}</span></td>
                    <td>{row.symbol}</td>
                    <td>{fmtPct(row.net_return_pct)}</td>
                    <td>{fmtPct(row.win_rate)}</td>
                    <td>{fmtPct(row.max_drawdown_pct)}</td>
                    <td>{row.total_trades ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>Latest Trades</h2>
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Mode</th>
                  <th>Direction</th>
                  <th>P/L $</th>
                  <th>P/L %</th>
                  <th>Exit Time</th>
                </tr>
              </thead>
              <tbody>
                {filteredTrades.slice(0, 20).map((row, idx) => (
                  <tr key={`${row.symbol}-${row.entry_time}-${idx}`}>
                    <td>{row.symbol}</td>
                    <td>{row.mode}</td>
                    <td>{row.direction}</td>
                    <td className={Number(row.dollar_pnl) >= 0 ? "up" : "down"}>{fmtCurrency(row.dollar_pnl)}</td>
                    <td className={Number(row.pnl_pct) >= 0 ? "up" : "down"}>{fmtPct(row.pnl_pct)}</td>
                    <td>{row.exit_time || "open"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>Guideline Audit</h2>
            <table>
              <thead>
                <tr>
                  <th>Mode</th>
                  <th>Symbol</th>
                  <th>Net Return</th>
                  <th>Win Rate</th>
                  <th>Max DD</th>
                  <th>Trades</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {latestResults.map((row, idx) => (
                  <tr key={`${row.mode}-${row.symbol}-${idx}`}>
                    <td><span className={`badge ${row.mode}`}>{row.mode}</span></td>
                    <td>{row.symbol}</td>
                    <td>{fmtPct(row.net_return_pct)}</td>
                    <td>{fmtPct(row.win_rate)}</td>
                    <td>{fmtPct(row.max_drawdown_pct)}</td>
                    <td>{row.total_trades ?? "-"}</td>
                    <td>{guidelineStatus(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <TradeGapAnalysis trades={filteredTrades} />
        </>
      )}
    </div>
  );
}
