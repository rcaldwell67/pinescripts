import React, { useMemo } from "react";

export default function TradeGapAnalysis({ trades }) {
  // trades: array of { symbol, version, mode, entry_time }
  // Only use version v6
  const results = useMemo(() => {
    if (!Array.isArray(trades)) return [];
    // Filter to only v6
    const v6trades = trades.filter(t => t.version === 'v6');
    // Group by symbol, version, mode
    const groups = new Map();
    const symbolDatesByMode = new Map();
    for (const r of v6trades) {
      const key = `${r.symbol}||${r.version}||${r.mode}`;
      if (!groups.has(key)) groups.set(key, { symbol: r.symbol, version: r.version, mode: r.mode, dates: [] });
      const raw = String(r.entry_time || '').trim();
      // Parse to YYYY-MM-DD
      let dateStr = null;
      try {
        const d = new Date(raw.endsWith('Z') || raw.includes('+') ? raw : raw + 'Z');
        if (!isNaN(d.getTime())) dateStr = d.toISOString().slice(0, 10);
      } catch {}
      if (!dateStr) {
        const prefix = raw.slice(0, 10);
        if (/^\d{4}-\d{2}-\d{2}$/.test(prefix)) dateStr = prefix;
      }
      if (!dateStr) continue;
      groups.get(key).dates.push(dateStr);
      const symbolKey = String(r.symbol || '');
      if (!symbolDatesByMode.has(symbolKey)) {
        symbolDatesByMode.set(symbolKey, { backtest: [], paper: [] });
      }
      const bucket = symbolDatesByMode.get(symbolKey);
      if (r.mode === 'backtest' || r.mode === 'paper') {
        bucket[r.mode].push(dateStr);
      }
    }
    // Compute max gap per symbol and per mode
    const symbolBest = new Map();
    function updateBest(symbol, slot, candidate) {
      const current = symbolBest.get(symbol) || {
        symbol,
        combined: null,
        backtest: null,
        paper: null,
        latestBacktestEntry: null,
        latestPaperEntry: null,
      };
      const prev = current[slot];
      if (!prev || candidate.gap > prev.gap) {
        current[slot] = candidate;
      }
      symbolBest.set(symbol, current);
    }
    for (const { symbol, version, mode, dates } of groups.values()) {
      const sorted = [...new Set(dates)].sort();
      for (let i = 1; i < sorted.length; i++) {
        const gap = (new Date(sorted[i]) - new Date(sorted[i - 1])) / 86400000;
        const candidate = { gap, from: sorted[i - 1], to: sorted[i], version, mode };
        updateBest(symbol, 'combined', candidate);
        if (mode === 'backtest' || mode === 'paper') {
          updateBest(symbol, mode, candidate);
        }
      }
    }
    for (const [symbol, byMode] of symbolDatesByMode.entries()) {
      const current = symbolBest.get(symbol) || {
        symbol,
        combined: null,
        backtest: null,
        paper: null,
        latestBacktestEntry: null,
        latestPaperEntry: null,
      };
      const backDates = [...new Set(byMode.backtest || [])].sort();
      const paperDates = [...new Set(byMode.paper || [])].sort();
      current.latestBacktestEntry = backDates.length ? backDates[backDates.length - 1] : null;
      current.latestPaperEntry = paperDates.length ? paperDates[paperDates.length - 1] : null;
      symbolBest.set(symbol, current);
    }
    const arr = [...symbolBest.values()].sort((a, b) => {
      const aGap = a.combined ? a.combined.gap : -1;
      const bGap = b.combined ? b.combined.gap : -1;
      return bGap - aGap;
    });
    return arr;
  }, [trades]);

  if (!results.length) return <div className="panel">No backtest or paper trade data found.</div>;
  const maxGap = Math.max(...results.map(r => (r.combined ? r.combined.gap : 0)), 0);
  return (
    <section className="panel">
      <h2>Trade Gap Analysis</h2>
      <p className="sub">Gaps are calendar days between consecutive entry dates. Combined Gap uses both backtest and paper rows. Backtest Gap and Paper Gap are computed independently so you can compare modes directly.</p>
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Combined Gap</th>
            <th>Backtest Gap</th>
            <th>Paper Gap</th>
            <th>Latest Backtest Entry</th>
            <th>Latest Paper Entry</th>
            <th>Worst Gap Context</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r, idx) => {
            const combined = r.combined;
            const backtest = r.backtest;
            const paper = r.paper;
            const combinedGap = combined ? combined.gap : null;
            const ratio = maxGap > 0 && combinedGap !== null ? combinedGap / maxGap : 0;
            const color = ratio > 0.7 ? '#f85149' : ratio > 0.4 ? '#ffa657' : '#3fb950';
            const gapCell = g => (g ? g.gap : '-');
            const combinedText = combined ? `${combined.mode} ${combined.version} (${combined.from} → ${combined.to})` : '-';
            return (
              <tr key={r.symbol + idx}>
                <td>{r.symbol}</td>
                <td style={{ color: combinedGap !== null ? color : undefined, fontWeight: 700 }}>{combinedGap ?? '-'}</td>
                <td>{gapCell(backtest)}</td>
                <td>{gapCell(paper)}</td>
                <td>{r.latestBacktestEntry || '-'}</td>
                <td>{r.latestPaperEntry || '-'}</td>
                <td>{combinedText}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
