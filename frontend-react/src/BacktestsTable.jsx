import React, { useEffect, useState } from "react";

// Guideline thresholds (sync with backend/config/guideline_policy.py)
const DEFAULT_THRESHOLDS = {
  min_trades: 2,
  min_win_rate_pct: 65.0,
  min_net_return_pct: 15.0,
  max_drawdown_pct: 4.5,
};

// Symbol/version-specific waivers (sync with backend/config/guideline_policy.py)
const POLICY_OVERRIDES = {
  'BTCUSDC:v1': { waived_hard_checks: new Set(['win_rate']) },
  'ETHUSDT:v3': { waived_hard_checks: new Set(['win_rate']) },
  'ETHUSDC:v3': { waived_hard_checks: new Set(['trades']) },
  ...Object.fromEntries(['v1','v2','v3','v4','v5','v6'].map(v => [
    `CLM:${v}`, { waived_hard_checks: new Set(['trades']) }
  ])),
  ...Object.fromEntries(['v1','v2','v3','v4','v5','v6'].map(v => [
    `CRF:${v}`, { waived_hard_checks: new Set(['trades']) }
  ])),
};

function normalizeSymbol(symbol) {
  return String(symbol || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

function getOverride(symbol, version) {
  const key = `${normalizeSymbol(symbol)}:${String(version || '').toLowerCase()}`;
  return POLICY_OVERRIDES[key];
}

function evaluateBacktestGuideline({ symbol, version = 'v6', trades, win_rate_pct, net_return_pct, max_drawdown_pct }) {
  const thresholds = DEFAULT_THRESHOLDS;
  const override = getOverride(symbol, version);
  const waived = override?.waived_hard_checks || new Set();
  const failures = [];
  const waivers = [];
  const checks = [
    ['trades', trades == null || trades < thresholds.min_trades, `trades<${thresholds.min_trades}`],
    ['win_rate', win_rate_pct == null || win_rate_pct < thresholds.min_win_rate_pct, `wr<${thresholds.min_win_rate_pct}`],
    ['net_return', net_return_pct == null || net_return_pct < thresholds.min_net_return_pct, `net<${thresholds.min_net_return_pct}`],
    ['max_drawdown', max_drawdown_pct == null || max_drawdown_pct > thresholds.max_drawdown_pct, `dd>${thresholds.max_drawdown_pct}`],
  ];
  for (const [check_key, failed, reason] of checks) {
    if (!failed) continue;
    if (waived.has(check_key)) waivers.push(`${reason} (advisory)`);
    else failures.push(reason);
  }
  const passed = failures.length === 0;
  const reasons = [...failures, ...waivers];
  return { passed, reasons };
}

export default function BacktestsTable() {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [assetTypeFilter, setAssetTypeFilter] = useState('');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [guidelineStatus, setGuidelineStatus] = useState('');
  const [timespan, setTimespan] = useState('YTD');

  useEffect(() => {
    async function loadSnapshot() {
      try {
        const res = await fetch("/pinescripts/data/dashboard_snapshot.json");
        if (!res.ok) throw new Error("Failed to load dashboard_snapshot.json");
        let data;
        try {
          data = await res.json();
        } catch (jsonErr) {
          throw new Error("Invalid JSON in dashboard_snapshot.json");
        }
        setSnapshot(data);
      } catch (err) {
        setError(err.message || "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    loadSnapshot();
  }, []);

  if (loading) return <section style={{ padding: 24 }}>Loading backtest data...</section>;
  if (error) return <section style={{ padding: 24, color: 'red' }}>Error: {error}</section>;
  if (!snapshot) return null;

  // Collect unique asset types for filter dropdown
  const assetTypes = Array.from(new Set(snapshot.symbols.map(s => s.asset_type || ''))).filter(Boolean);
  // Collect unique symbols for filter dropdown
  const symbols = Array.from(new Set(snapshot.symbols.map(s => s.symbol)));

  // Filtering logic
  const filteredSymbols = snapshot.symbols.filter(sym => {
    if (assetTypeFilter && sym.asset_type !== assetTypeFilter) return false;
    if (symbolFilter && sym.symbol !== symbolFilter) return false;
    const result = snapshot.results.backtest.find(r => r.symbol_key === sym.symbol_key);
    if (guidelineStatus) {
      const audit = result ? evaluateBacktestGuideline({
        symbol: sym.symbol,
        version: 'v6',
        trades: result.total_trades,
        win_rate_pct: result.win_rate,
        net_return_pct: result.net_return_pct,
        max_drawdown_pct: result.max_drawdown_pct,
      }) : null;
      if (guidelineStatus === 'pass' && !(audit && audit.passed)) return false;
      if (guidelineStatus === 'fail' && !(audit && !audit.passed)) return false;
    }
    return true;
  });

  return (
    <section style={{ padding: 24 }}>
      <h2>Backtests (v6) - Active Symbols</h2>
      <div style={{ marginBottom: 16, display: 'flex', gap: 16, alignItems: 'center' }}>
        <label>
          Timespan:
          <select value={timespan} onChange={e => setTimespan(e.target.value)} style={{ marginLeft: 8 }}>
            <option value="YTD">YTD</option>
            <option value="MTD">MTD</option>
            <option value="WTD">WTD</option>
            <option value="1D">1D</option>
            <option value="4H">4H</option>
          </select>
        </label>
        <label>
          Asset Type:
          <select value={assetTypeFilter} onChange={e => setAssetTypeFilter(e.target.value)} style={{ marginLeft: 8 }}>
            <option value="">All</option>
            {assetTypes.map(type => <option key={type} value={type}>{type}</option>)}
          </select>
        </label>
        <label>
          Symbol:
          <select value={symbolFilter} onChange={e => setSymbolFilter(e.target.value)} style={{ marginLeft: 8 }}>
            <option value="">All</option>
            {symbols.map(sym => <option key={sym} value={sym}>{sym}</option>)}
          </select>
        </label>
        <label>
          Guideline Status:
          <select value={guidelineStatus} onChange={e => setGuidelineStatus(e.target.value)} style={{ marginLeft: 8 }}>
            <option value="">All</option>
            <option value="pass">Pass</option>
            <option value="fail">Fail</option>
          </select>
        </label>
      </div>
      <div style={{overflowX: 'auto'}}>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
          <thead>
            <tr style={{background: 'var(--bg-mid)'}}>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Symbol</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Asset Type</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Current Equity</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Net Return %</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Win Rate</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Max Drawdown %</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Total Trades</th>
              <th style={{padding: '8px 12px', textAlign: 'right'}}>Last Updated</th>
              <th style={{padding: '8px 12px', textAlign: 'center'}}>Guideline Audit</th>
            </tr>
          </thead>
          <tbody>
            {filteredSymbols.map(sym => {
              const result = snapshot.results.backtest.find(r => r.symbol_key === sym.symbol_key);
              const audit = result ? evaluateBacktestGuideline({
                symbol: sym.symbol,
                version: 'v6',
                trades: result.total_trades,
                win_rate_pct: result.win_rate,
                net_return_pct: result.net_return_pct,
                max_drawdown_pct: result.max_drawdown_pct,
              }) : null;
              return (
                <tr key={sym.symbol_key}>
                  <td style={{padding: '8px 12px'}}>{sym.symbol}</td>
                  <td style={{padding: '8px 12px'}}>{sym.asset_type || '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.current_equity ?? '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.net_return_pct != null ? result.net_return_pct.toFixed(2) + '%' : '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.win_rate != null ? result.win_rate.toFixed(1) + '%' : '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.max_drawdown_pct != null ? result.max_drawdown_pct.toFixed(2) + '%' : '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.total_trades ?? '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.timestamp ?? '-'}</td>
                  <td style={{padding: '8px 12px', textAlign: 'center'}}>
                    {result ? (
                      audit.passed ? (
                        <span style={{color: 'green', fontWeight: 600}}>PASS</span>
                      ) : (
                        <span style={{color: 'red', fontWeight: 600}} title={audit.reasons.join(', ')}>
                          FAIL
                          <span style={{fontWeight: 400, color: '#a00', marginLeft: 6, fontSize: '0.9em'}}>
                            {audit.reasons.join(', ')}
                          </span>
                        </span>
                      )
                    ) : '-'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <footer style={{marginTop: 24, textAlign: 'right', color: '#888', fontSize: '0.95em'}}>
        Dashboard snapshot generated at: {snapshot.generated_at ? new Date(snapshot.generated_at).toLocaleString() : '-'}
      </footer>
    </section>
  );
}