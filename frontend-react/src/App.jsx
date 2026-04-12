
import React, { useState } from "react";

// Demo/mock data from backend/data/print_account_info.py output
const MOCK_ACCOUNTS = [
  {
    account_id: '707a2217-c864-4f3c-9ead-f92492b3f594',
    account_number: 'PA31PQ1D1H6F',
    currency: 'USD',
    status: 'ACTIVE',
    beginning_balance: 100000.0,
    current_balance: 100000.0,
    buying_power: 200000.0,
    cash: 100000.0,
    last_event: 'heartbeat',
    updated_at: '2026-04-08T17:55:32.503574+00:00',
    account_mode: 'paper',
  },
  {
    account_id: 'c8130dac-a2e0-4584-9b1b-b7879106e74b',
    account_number: '920404453',
    currency: 'USD',
    status: 'ACTIVE',
    beginning_balance: 0.0,
    current_balance: 0.0,
    buying_power: 0.0,
    cash: 0.0,
    last_event: 'live:post_sync',
    updated_at: '2026-04-03T00:28:59.590048+00:00',
    account_mode: 'live',
  },
];

function App() {
  const [activePage, setActivePage] = useState("Dashboard");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const handleNav = (page) => {
    if (page === "Settings") setSettingsOpen((v) => !v);
    else {
      setActivePage(page);
      setSettingsOpen(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <nav>
          <ul>
            <li><a href="#" onClick={() => handleNav("Dashboard")}>Dashboard</a></li>
            <li><a href="#" onClick={() => handleNav("Backtests")}>Backtests</a></li>
            <li><a href="#" onClick={() => handleNav("Paper Trading")}>Paper Trading</a></li>
            <li><a href="#" onClick={() => handleNav("Live Trading")}>Live Trading</a></li>
            <li><a href="#" onClick={() => handleNav("Charts")}>Charts</a></li>
            <li>
              <a href="#" onClick={() => handleNav("Settings")}>Settings</a>
              {settingsOpen && (
                <ul className="submenu">
                  <li><a href="#" onClick={() => setActivePage("Account Info")}>Account Info</a></li>
                </ul>
              )}
            </li>
          </ul>
        </nav>
      </aside>
      <div className="main-content">
        <header className="app-header">
          <span className="app-title">Dashboard App</span>
        </header>
        <main>
          {activePage === "Account Info" ? (
            <section style={{ padding: 24 }}>
              <h2>Account Info</h2>
              <div className="account-info-grid">
                {['paper', 'live'].map((mode) => {
                  const acc = MOCK_ACCOUNTS.find(a => a.account_mode === mode);
                  return (
                    <div className="account-card" key={mode}>
                      <h3>{mode === 'paper' ? 'Paper Account' : 'Live Account'}</h3>
                      {acc ? (
                        <table style={{ width: '100%', fontSize: '1em', marginTop: 8 }}>
                          <tbody>
                            <tr><td><b>Account #</b></td><td>{acc.account_number}</td></tr>
                            <tr><td><b>Status</b></td><td>{acc.status}</td></tr>
                            <tr><td><b>Currency</b></td><td>{acc.currency}</td></tr>
                            <tr><td><b>Current Balance</b></td><td>{acc.current_balance}</td></tr>
                            <tr><td><b>Buying Power</b></td><td>{acc.buying_power}</td></tr>
                            <tr><td><b>Cash</b></td><td>{acc.cash}</td></tr>
                            <tr><td><b>Last Event</b></td><td>{acc.last_event}</td></tr>
                            <tr><td><b>Updated At</b></td><td>{acc.updated_at}</td></tr>
                          </tbody>
                        </table>
                      ) : (
                        <p>No account info found.</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          ) : activePage === "Backtests" ? (
            <section style={{ padding: 24 }}>
              <h2>Backtests (v6) - Active Symbols</h2>
              <div style={{overflowX: 'auto'}}>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
                  <thead>
                    <tr style={{background: 'var(--bg-mid)'}}>
                      <th style={{padding: '8px 12px', textAlign: 'left'}}>Symbol</th>
                      <th style={{padding: '8px 12px', textAlign: 'right'}}>Current Equity</th>
                      <th style={{padding: '8px 12px', textAlign: 'right'}}>Net Return %</th>
                      <th style={{padding: '8px 12px', textAlign: 'right'}}>Win Rate</th>
                      <th style={{padding: '8px 12px', textAlign: 'right'}}>Total Trades</th>
                      <th style={{padding: '8px 12px', textAlign: 'right'}}>Last Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { symbol: "BTC/USD", symbol_key: "BTCUSD" },
                      { symbol: "BTC/USDC", symbol_key: "BTCUSDC" },
                      { symbol: "BTC/USDT", symbol_key: "BTCUSDT" },
                      { symbol: "CLM", symbol_key: "CLM" },
                      { symbol: "CRF", symbol_key: "CRF" },
                      { symbol: "ETH/BTC", symbol_key: "ETHBTC" },
                      { symbol: "ETH/USD", symbol_key: "ETHUSD" },
                      { symbol: "ETH/USDC", symbol_key: "ETHUSDC" },
                      { symbol: "ETH/USDT", symbol_key: "ETHUSDT" },
                      { symbol: "QQQ", symbol_key: "QQQ" },
                      { symbol: "SPY", symbol_key: "SPY" },
                    ].map(sym => {
                      const result = require('../frontend-react/public/data/dashboard_snapshot.json').results.backtest.find(r => r.symbol_key === sym.symbol_key);
                      return (
                        <tr key={sym.symbol_key}>
                          <td style={{padding: '8px 12px'}}>{sym.symbol}</td>
                          <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.current_equity ?? '-'}</td>
                          <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.net_return_pct != null ? result.net_return_pct.toFixed(2) + '%' : '-'}</td>
                          <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.win_rate != null ? result.win_rate.toFixed(1) + '%' : '-'}</td>
                          <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.total_trades ?? '-'}</td>
                          <td style={{padding: '8px 12px', textAlign: 'right'}}>{result?.timestamp ?? '-'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <section style={{ padding: 24 }}>
              <h2>Account Overview</h2>
              <div className="account-info-grid">
                {['paper', 'live'].map((mode) => {
                  const acc = MOCK_ACCOUNTS.find(a => a.account_mode === mode);
                  return (
                    <div className="account-card" key={mode}>
                      <h3>{mode === 'paper' ? 'Paper Trading' : 'Live Trading'}</h3>
                      {acc ? (
                        <table style={{ width: '100%', fontSize: '1.1em', marginTop: 8 }}>
                          <tbody>
                            <tr><td><b>Current Balance</b></td><td>{acc.current_balance}</td></tr>
                            <tr><td><b>Buying Power</b></td><td>{acc.buying_power}</td></tr>
                          </tbody>
                        </table>
                      ) : (
                        <p>No account info found.</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </main>
        <footer className="app-footer">
          <span>© {new Date().getFullYear()} Trading Dashboard</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
