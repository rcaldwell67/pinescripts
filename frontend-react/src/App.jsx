
import React from "react";

function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <nav>
          <ul>
            <li><a href="#">Dashboard</a></li>
            <li><a href="#">Backtests</a></li>
            <li><a href="#">Live Trading</a></li>
            <li><a href="#">Settings</a></li>
          </ul>
        </nav>
      </aside>
      <div className="main-content">
        <header className="app-header">
          <span className="app-title">Dashboard App</span>
        </header>
        <main>
          <p>The app is now restored to a minimal, valid state. You can re-add dashboard features incrementally.</p>
        </main>
        <footer className="app-footer">
          <span>© {new Date().getFullYear()} Trading Dashboard</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
