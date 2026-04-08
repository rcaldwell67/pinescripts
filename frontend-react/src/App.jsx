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

  return (
    <div className="page-shell">
      <div className="bg-grid" />
      <header className="topbar">
        <div>
          <p className="eyebrow">PulseBoard</p>
          <h1>Crypto + ETF Trading Monitor</h1>
          <p className="sub">Unified backtest, paper, and live observability from Alpaca + Backtrader.</p>
        </div>
        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px'}}>
          <a
            href="/dashboard.html"
            className="chip"
            style={{
              background: '#2ad4ff',
              color: '#181c20',
              fontWeight: 700,
              borderRadius: 8,
              padding: '10px 20px',
              textDecoration: 'none',
              marginBottom: '6px',
              border: 'none',
              fontSize: '14px',
              boxShadow: '0 2px 8px #0002',
              transition: 'background 0.2s',
              display: 'inline-block',
              textAlign: 'center',
              cursor: 'pointer',
            }}
            tabIndex={0}
          >
            Dashboard Switcher
          </a>
          <div className="chip">Snapshot: {snapshot?.generated_at || "-"}</div>
        </div>
      </header>

      <section className="controls">
        <label>
          Symbol
          <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}>
            {symbolOptions.map((symbol) => (
              <option key={symbol} value={symbol}>
                {symbol}
              </option>
            ))}
          </select>
        </label>
        <label>
          Asset Class
          <select value={assetFilter} onChange={(e) => setAssetFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="crypto">Crypto</option>
            <option value="etf">ETF</option>
          </select>
        </label>
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
