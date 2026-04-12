
import React, { useState } from "react";

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
                <div className="account-card">
                  <h3>Paper Account</h3>
                  <p>Account information will be displayed here.</p>
                </div>
                <div className="account-card">
                  <h3>Live Account</h3>
                  <p>Account information will be displayed here.</p>
                </div>
              </div>
            </section>
          ) : (
            <p>The app is now restored to a minimal, valid state. You can re-add dashboard features incrementally.</p>
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
