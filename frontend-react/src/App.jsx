import { useEffect, useMemo, useState } from "react";
import initSqlJs from 'sql.js';
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

const DASHBOARD_TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'transactions', label: 'All Transactions' },
  { key: 'charts', label: 'Charts' },
  { key: 'tradeLog', label: 'Trade Log' },
  { key: 'logs', label: 'Logs' },
];


function App() {
    // Guideline audit mode: backtest, paper, or live
    const [auditMode, setAuditMode] = useState('backtest');
  // Remove snapshot state, add states for trades, results, and account
  const [trades, setTrades] = useState([]);
  const [results, setResults] = useState({ backtest: [], paper: [], live: [] });
  const [account, setAccount] = useState({});
  const [symbolFilter, setSymbolFilter] = useState("ALL");
  const [assetFilter, setAssetFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeSymbols, setActiveSymbols] = useState([]); // active=1
  const [inactiveSymbols, setInactiveSymbols] = useState([]); // active=0
  const [activeTab, setActiveTab] = useState('overview');
  // Filters for All Transactions
  const [filterVersion, setFilterVersion] = useState('');
  const [filterTimeframe, setFilterTimeframe] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterDirection, setFilterDirection] = useState('');
  const [filterType, setFilterType] = useState('');
  const [pageSize, setPageSize] = useState(50);
  const [selectedAlpacaSymbol, setSelectedAlpacaSymbol] = useState("");
  const [alpacaLoading, setAlpacaLoading] = useState(false);
  // Only filter by crypto for Add Alpaca Symbol
  const [cryptoOnly, setCryptoOnly] = useState(false);

  // Load active dashboard symbols from 'symbols' table for Symbol combobox
  useEffect(() => {
    async function loadActiveSymbols() {
      setAlpacaLoading(true);
      try {
        const dbPath = `${import.meta.env.BASE_URL}data/tradingcopilot.db`;
        const dbRes = await fetch(dbPath);
        if (!dbRes.ok) throw new Error("Failed to fetch tradingcopilot.db");
        const dbBuffer = await dbRes.arrayBuffer();
        const SQL = await initSqlJs({ locateFile: file => `${import.meta.env.BASE_URL}sql-wasm.wasm` });
        const db = new SQL.Database(new Uint8Array(dbBuffer));
        // Query all active symbols from symbols table (active=1)
        const resSymbols = db.exec("SELECT symbol, description, asset_class FROM symbols WHERE active=1");
        let dashboardSyms = [];
        if (resSymbols.length > 0) {
          const cols = resSymbols[0].columns;
          const values = resSymbols[0].values;
          dashboardSyms = values.map(row => {
            const obj = {};
            cols.forEach((col, i) => { obj[col] = row[i]; });
            return obj;
          });
        }
        setActiveSymbols(dashboardSyms);
        setInactiveSymbols([]);
      } catch (e) {
        setActiveSymbols([]);
        setInactiveSymbols([]);
      } finally {
        setAlpacaLoading(false);
      }
    }
    loadActiveSymbols();
  }, []);

  // Load all dashboard data from tradingcopilot.db
  useEffect(() => {
    async function loadDashboardData() {
      setLoading(true);
      setError("");
      try {
        const dbPath = `${import.meta.env.BASE_URL}data/tradingcopilot.db`;
        const dbRes = await fetch(dbPath);
        if (!dbRes.ok) throw new Error("Failed to fetch tradingcopilot.db");
        const dbBuffer = await dbRes.arrayBuffer();
        // Use correct WASM path for GitHub Pages deployment
        const SQL = await initSqlJs({ locateFile: file => `${import.meta.env.BASE_URL}sql-wasm.wasm` });
        const db = new SQL.Database(new Uint8Array(dbBuffer));

        // Trades table
        const resTrades = db.exec("SELECT * FROM trades");
        let tradesArr = [];
        if (resTrades.length > 0) {
          const cols = resTrades[0].columns;
          const values = resTrades[0].values;
          tradesArr = values.map(row => {
            const obj = {};
            cols.forEach((col, i) => { obj[col] = row[i]; });
            return obj;
          });
        }
        setTrades(tradesArr);

        // Results table (assume a 'results' table with mode column)
        const resResults = db.exec("SELECT * FROM results");
        let resultsObj = { backtest: [], paper: [], live: [] };
        if (resResults.length > 0) {
          const cols = resResults[0].columns;
          const values = resResults[0].values;
          const allResults = values.map(row => {
            const obj = {};
            cols.forEach((col, i) => { obj[col] = row[i]; });
            return obj;
          });
          resultsObj.backtest = allResults.filter(r => r.mode === 'backtest');
          resultsObj.paper = allResults.filter(r => r.mode === 'paper');
          resultsObj.live = allResults.filter(r => r.mode === 'live');
        }
        setResults(resultsObj);

        // Account table (assume only one row)
        const resAccount = db.exec("SELECT * FROM account LIMIT 1");
        let accountObj = {};
        if (resAccount.length > 0) {
          const cols = resAccount[0].columns;
          const values = resAccount[0].values;
          if (values.length > 0) {
            cols.forEach((col, i) => { accountObj[col] = values[0][i]; });
          }
        }
        setAccount(accountObj);
      } catch (err) {
        setError(`Failed to load dashboard data: ${String(err?.message || err)}`);
        setTrades([]);
        setResults({ backtest: [], paper: [], live: [] });
        setAccount({});
      } finally {
        setLoading(false);
      }
    }
    loadDashboardData();
  }, []);

  // Use only active dashboard symbols for Symbol combobox
  const symbols = activeSymbols;
  // Sort symbol options alphabetically, keeping 'ALL' first
  const sortedSymbols = Array.from(new Set(symbols.map((s) => s.symbol))).filter(s => s !== "ALL").sort((a, b) => a.localeCompare(b));
  const symbolOptions = ["ALL", ...sortedSymbols];

  const filteredTrades = useMemo(() => {
    const v6trades = trades.filter(t => t.version === 'v6');
    return v6trades.filter((t) => {
      const symbolOk = symbolFilter === "ALL" || t.symbol === symbolFilter;
      const assetOk = assetFilter === "all" || t.asset_class === assetFilter;
      return symbolOk && assetOk;
    });
  }, [trades, symbolFilter, assetFilter]);

  const latestResults = useMemo(() => {
    const resultsArr = [];
    for (const row of (results[auditMode] || []).filter(r => r.version === 'v6')) {
      const symbolOk = symbolFilter === "ALL" || row.symbol === symbolFilter;
      const asset = symbols.find((s) => s.symbol === row.symbol)?.asset_class || "etf";
      const assetOk = assetFilter === "all" || asset === assetFilter;
      if (symbolOk && assetOk) {
        resultsArr.push({ ...row, asset_class: asset });
      }
    }
    return resultsArr;
  }, [results, symbolFilter, assetFilter, symbols, auditMode]);

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
  function matchesCryptoFilter(sym) {
    const assetClass = (sym.asset_class || '').toLowerCase();
    if (cryptoOnly) return assetClass === 'crypto';
    return true;
  }
  // Load all Alpaca symbols and filter to only those not active in the dashboard
  const [allAlpacaSymbols, setAllAlpacaSymbols] = useState([]);
  useEffect(() => {
    async function loadAllAlpacaSymbols() {
      try {
        const dbPath = `${import.meta.env.BASE_URL}data/tradingcopilot.db`;
        const dbRes = await fetch(dbPath);
        if (!dbRes.ok) throw new Error("Failed to fetch tradingcopilot.db");
        const dbBuffer = await dbRes.arrayBuffer();
        const SQL = await initSqlJs({ locateFile: file => `${import.meta.env.BASE_URL}sql-wasm.wasm` });
        const db = new SQL.Database(new Uint8Array(dbBuffer));
        // Get all symbols from alpaca_symbols
        const resAlpaca = db.exec("SELECT symbol, name as description, type as asset_class FROM alpaca_symbols");
        let allSyms = [];
        if (resAlpaca.length > 0) {
          const cols = resAlpaca[0].columns;
          const values = resAlpaca[0].values;
          allSyms = values.map(row => {
            const obj = {};
            cols.forEach((col, i) => { obj[col] = row[i]; });
            return obj;
          });
        }
        setAllAlpacaSymbols(allSyms);
      } catch (e) {
        setAllAlpacaSymbols([]);
      }
    }
    loadAllAlpacaSymbols();
  }, []);

  // Only show Alpaca symbols not already active in dashboard, filtered by cryptoOnly
  const dashboardSymbolsSet = new Set(symbols.map(s => s.symbol));
  let availableAlpacaSymbols = [];
  if (cryptoOnly) {
    // Only crypto symbols
    availableAlpacaSymbols = allAlpacaSymbols
      .filter(sym => !dashboardSymbolsSet.has(sym.symbol) && (sym.asset_class || '').toLowerCase() === 'crypto')
      .sort((a, b) => a.symbol.localeCompare(b.symbol));
  } else {
    // Only non-crypto symbols
    availableAlpacaSymbols = allAlpacaSymbols
      .filter(sym => !dashboardSymbolsSet.has(sym.symbol) && (sym.asset_class || '').toLowerCase() !== 'crypto')
      .sort((a, b) => a.symbol.localeCompare(b.symbol));
  }

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

  // Remove noisy console warnings for empty Alpaca symbol list
  useEffect(() => {}, [availableAlpacaSymbols, symbols, cryptoOnly, inactiveSymbols]);

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
      { name: "Win", value: wins },
      { name: "Loss", value: losses },
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

  return (
    <div className="page-shell">
      <div className="bg-grid" />
      <header className="topbar">
        <div>
          <p className="eyebrow">PulseBoard</p>
          <h1>Crypto + ETF Trading Monitor</h1>
          <p className="sub">Unified backtest, paper, and live observability from Alpaca + Backtrader.</p>
        </div>
        <div className="chip">Snapshot: {account?.generated_at || "-"}</div>
      </header>

      <section className="controls" style={{ alignItems: 'end', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label>Symbol
            <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}>
              {symbolOptions.map((symbol, idx) => (
                <option key={symbol === "ALL" ? "ALL" : symbol} value={symbol}>{symbol}</option>
              ))}
            </select>
          </label>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label>Add Alpaca Symbol</label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ color: '#9bb4c7', fontSize: 13, marginRight: 8 }}>
              {alpacaLoading ? 'Loading symbols...' : `Available: ${availableAlpacaSymbols.length}`}
            </span>
            <select
              value={selectedAlpacaSymbol}
              onChange={e => setSelectedAlpacaSymbol(e.target.value)}
              disabled={alpacaLoading || availableAlpacaSymbols.length === 0}
              style={{ minWidth: 120 }}
            >
              <option value="">{alpacaLoading ? "Loading..." : availableAlpacaSymbols.length === 0 ? "No symbols available" : "Select..."}</option>
              {availableAlpacaSymbols.map(sym => (
                <option key={sym.symbol} value={sym.symbol}>{sym.symbol}</option>
              ))}
            </select>
            <button
              type="button"
              style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid var(--edge)', background: 'var(--aqua)', color: '#181c20', fontWeight: 600, cursor: 'pointer' }}
              onClick={handleAddSymbol}
              disabled={!selectedAlpacaSymbol}
            >Add</button>
            <button
              type="button"
              style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #f85149', background: '#f85149', color: '#fff', fontWeight: 600, cursor: symbolFilter && symbolFilter !== 'ALL' ? 'pointer' : 'not-allowed', opacity: symbolFilter && symbolFilter !== 'ALL' ? 1 : 0.4, marginLeft: 0 }}
              onClick={handleRemoveSymbol}
              disabled={!symbolFilter || symbolFilter === 'ALL'}
              title="Request removal of selected symbol from dashboard"
            >Remove</button>
            <div style={{ display: 'flex', gap: 8, marginLeft: 8 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={cryptoOnly}
                  onChange={e => setCryptoOnly(e.target.checked)}
                /> Crypto only
              </label>
            </div>
            {alpacaLoading && <span style={{ color: '#ffa657', fontSize: 13 }}>Loading symbols...</span>}
            {!alpacaLoading && availableAlpacaSymbols.length === 0 && (
              <span style={{ color: '#ffa657', fontSize: 13, marginLeft: 8 }}>
                All Alpaca symbols are already in the dashboard or filtered out.
              </span>
            )}
          </div>
        </div>
      </section>

      {loading && <div className="panel">Loading dashboard data...</div>}
      {error && <div className="panel error">{error}</div>}

      {!loading && !error && (
        <>
          {/* Dashboard Tabs */}
          <nav style={{ display: 'flex', gap: 12, marginBottom: 18 }}>
            {DASHBOARD_TABS.map(tab => (
              <button
                key={tab.key}
                className={activeTab === tab.key ? 'mode-btn active' : 'mode-btn'}
                style={{ fontWeight: activeTab === tab.key ? 700 : 400, fontSize: 15, padding: '8px 18px', borderRadius: 8, border: '1px solid var(--edge)', background: activeTab === tab.key ? 'var(--aqua)' : 'rgba(0,0,0,0.12)', color: activeTab === tab.key ? '#181c20' : 'var(--text)', cursor: 'pointer' }}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </nav>

          {/* Tab Content */}
          {activeTab === 'overview' && (
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
              <section className="panel">
                <h2>Guideline Audit</h2>
                <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                  {['backtest', 'paper', 'live'].map(mode => (
                    <button
                      key={mode}
                      className={auditMode === mode ? 'mode-btn active' : 'mode-btn'}
                      style={{ fontWeight: auditMode === mode ? 700 : 400, fontSize: 14, padding: '6px 16px', borderRadius: 8, border: '1px solid var(--edge)', background: auditMode === mode ? 'var(--aqua)' : 'rgba(0,0,0,0.12)', color: auditMode === mode ? '#181c20' : 'var(--text)', cursor: 'pointer' }}
                      onClick={() => setAuditMode(mode)}
                    >
                      {mode.charAt(0).toUpperCase() + mode.slice(1)}
                    </button>
                  ))}
                </div>
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
          {activeTab === 'transactions' && (
            <section className="panel">
              <h2>All Transactions</h2>
              {/* Filters UI */}
              <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
                <select style={{ minWidth: 120 }} value={filterVersion} onChange={e => setFilterVersion(e.target.value)}>
                  <option value="">Version</option>
                  {[...new Set(filteredTrades.map(t => t.mode))].map(v => v && <option key={v} value={v}>{v}</option>)}
                </select>
                <select style={{ minWidth: 120 }} value={filterTimeframe} onChange={e => setFilterTimeframe(e.target.value)}>
                  <option value="">Timeframe</option>
                  {[...new Set(filteredTrades.map(t => t.timeframe))].map(tf => tf && <option key={tf} value={tf}>{tf}</option>)}
                </select>
                <select style={{ minWidth: 120 }} value={filterAction} onChange={e => setFilterAction(e.target.value)}>
                  <option value="">Action</option>
                  {[...new Set(filteredTrades.map(t => t.action))].map(a => a && <option key={a} value={a}>{a}</option>)}
                </select>
                <select style={{ minWidth: 120 }} value={filterDirection} onChange={e => setFilterDirection(e.target.value)}>
                  <option value="">Direction</option>
                  {[...new Set(filteredTrades.map(t => t.direction))].map(d => d && <option key={d} value={d}>{d}</option>)}
                </select>
                <select style={{ minWidth: 120 }} value={filterType} onChange={e => setFilterType(e.target.value)}>
                  <option value="">Type</option>
                  {[...new Set(filteredTrades.map(t => t.type))].map(tp => tp && <option key={tp} value={tp}>{tp}</option>)}
                </select>
                <select style={{ minWidth: 120 }} value={pageSize} onChange={e => setPageSize(Number(e.target.value))}>
                  {[20, 50, 100, 200].map(sz => <option key={sz} value={sz}>{sz} / page</option>)}
                </select>
              </div>
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
                  {filteredTrades
                    .filter(row => !filterVersion || row.mode === filterVersion)
                    .filter(row => !filterTimeframe || row.timeframe === filterTimeframe)
                    .filter(row => !filterAction || row.action === filterAction)
                    .filter(row => !filterDirection || row.direction === filterDirection)
                    .filter(row => !filterType || row.type === filterType)
                    .slice(0, pageSize)
                    .map((row, idx) => (
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
          )}
          {activeTab === 'charts' && (
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
          )}
          {/* TODO: Implement Trade Log and Logs tabs */}
        </>
      )}
    </div>
  );
}

export default App;
