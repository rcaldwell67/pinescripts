
console.log('[DEBUG] Script loaded: top of <script> tag');
console.log('[DEBUG] Before DOMContentLoaded event handler registration');
let INSTRUMENTS = {};
// Utility to build symbol switcher buttons dynamically (if used)
function buildSymbolSwitcher(symbols) {
  const switcher = document.querySelector('.sym-switcher');
  if (!switcher) return;
  // Remove all children except the label, select, input, and add button
  const keepIds = ['symbolSelect', 'alpacaSymbolSelect', 'alpacaTypeFilters', 'loadAlpacaSymbolsBtn', 'addSymbolBtn', 'removeSymbolBtn'];

  Array.from(switcher.children).forEach(child => {
    if (child.tagName === 'LABEL' || keepIds.includes(child.id)) return;
    switcher.removeChild(child);
  });
  // Optionally, add symbol buttons dynamically (if you want buttons in addition to the select)
  // (Commented out for now)
}

function buildInstruments(symbols) {

  // Build the instruments object dynamically using naming conventions
  const instruments = {};
  const versionTemplates = [
    { key: 'v1', label: 'v1 - 5m Shorts', tf: '5m', color: '#58a6ff' },
    { key: 'v2', label: 'v2 - 10m Both', tf: '10m', color: '#3fb950' },
    { key: 'v3', label: 'v3 - 15m Shorts', tf: '15m', color: '#ffa657' },
    { key: 'v4', label: 'v4 - 30m Both', tf: '30m', color: '#bc8cff' },
    { key: 'v5', label: 'v5 - 1h Longs', tf: '1h', color: '#d29922' },
    { key: 'v6', label: 'v6 - 1D Both', tf: '1D', color: '#ff7b72' }
  ];
  symbols.forEach(sym => {
    // Normalize symbol for file paths
    const fileSym = sym.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
    // Label: SYMBOL_KEY -> SYMBOL-LABEL
    const label = sym.replace(/_/g, '-');
    const versions = {};
    versionTemplates.forEach(vt => {
      versions[vt.key] = {
        label: vt.label,
        tf: vt.tf,
        color: vt.color,
        file: `data/${fileSym}/${vt.key}_trades.csv`,
        paperFile: `data/${fileSym}/${vt.key}_trades_paper.csv`,
        liveFile: `data/${fileSym}/${vt.key}_trades_live.csv`,
        pnlCol: 'dollar_pnl',
        equityCol: 'equity',
        resultCol: vt.key === 'v6' ? 'exit_reason' : 'result',
        dirCol: 'direction',
        entryCol: 'entry',
        exitCol: 'exit',
        entryTimeCol: 'entry_time',
        exitTimeCol: 'exit_time',
        ...(vt.key === 'v1' || vt.key === 'v2' ? {
          backtestVariants: {
            main: { label: 'Main', file: `data/${fileSym}/${vt.key}_trades.csv` },
            '12mo': { label: '12mo', file: `data/${fileSym}/${vt.key}_trades_12mo.csv` }
          }
        } : {}),
        ...(vt.key === 'v6' ? { hasYear: true } : {})
      };
    });
    instruments[sym] = { label, versions };
  });
  return instruments;
}

function initStateObjects(symbols) {
  // For each mode, create an object with all symbols as keys
  const modes = ['backtest', 'paper', 'live'];
  _modeCache = {};
  modes.forEach(mode => {
    _modeCache[mode] = {};
    symbols.forEach(sym => {
      _modeCache[mode][sym] = {};
    });
  });
  loaded = _modeCache['backtest']; // Always set loaded after _modeCache is built
  // For backtestSelections, initialize for all symbols
  window.backtestSelections = {};

  symbols.forEach(sym => {
    window.backtestSelections[sym] = {};
    // Optionally, set defaults for known versions
    if (INSTRUMENTS[sym] && INSTRUMENTS[sym].versions) {
      Object.keys(INSTRUMENTS[sym].versions).forEach(ver => {
        window.backtestSelections[sym][ver] = 'main';
      });
    }
  });
}

let loaded; // Global reference to the currently loaded data for the active mode
let _modeCache;
let activeMode = 'backtest';
let activeSym = '';
let activeTab = 'all';
let charts = {};
let tradeTablePage = 1;
let tradePageSize = 25;
let txPage = 1;
let txPageSize = 25;
const PAPER_TRADING_SUPPORTED_VERSIONS = new Set(['v1']);
const LIVE_TRADING_SUPPORTED_VERSIONS = new Set(['v1']);
let pendingDatasetSymbol = '';

function getSymbolAliases(sym) {
  const raw = String(sym || '').trim();
  if (!raw) return [];
  const slash = raw.replace(/_/g, '/').toUpperCase();
  const underscore = raw.replace(/[^A-Za-z0-9]/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '').toUpperCase();
  return [...new Set([raw.toUpperCase(), slash, underscore])];
}

function getNormalizedSymbolKey(sym) {
  return String(sym || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}



  // --- Dataset selector logic ---
  let activeDataset = 'backtest'; // 'backtest' or 'paper';
  function getResultsJsonFile() {
    return activeDataset === 'backtest' ? 'data/backtest_results.json' : 'data/paper_trading_results.json';
  }

  function addDatasetSelector() {
    const wrap = document.getElementById('datasetModeButtons');
    if (!wrap) return;

    const buttons = wrap.querySelectorAll('.mode-btn');
    buttons.forEach(btn => {
      if (btn.dataset.bound === '1') return;
      btn.dataset.bound = '1';
      btn.addEventListener('click', () => {
        const nextDataset = btn.dataset.mode;
        if (!nextDataset || nextDataset === activeDataset) return;
        const currentSelect = document.getElementById('symbolSelect');
        pendingDatasetSymbol = (currentSelect && currentSelect.value) || activeSym || '';
        activeDataset = nextDataset;
        activeMode = activeDataset;
        resetTransactionFilters();
        addDatasetSelector();
        loadSymbolsAndInit();
      });
    });

    buttons.forEach(btn => {
      const isActive = btn.dataset.mode === activeDataset;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  // --- New: Load symbols and results from selected dataset JSON ---
  async function loadSymbolsAndInit() {
    activeMode = activeDataset;
    addDatasetSelector();
    console.log('[DEBUG] loadSymbolsAndInit called');
    if (typeof window.initSqlJs === 'undefined') {
      console.error('[DEBUG] sql.js not loaded');
      throw new Error('sql.js not loaded');
    }
    // Fetch the SQLite database file with fallback logic
    const dbPaths = ['data/tradingcopilot.db', 'docs/data/tradingcopilot.db'];
    let dbReq = null, dbPathUsed = '';
    for (const dbPath of dbPaths) {
      try {
        console.log('[DEBUG] window.location.href:', window.location.href);
        // Add cache-busting query string
        const cacheBustedPath = dbPath + '?v=' + Date.now();
        const resolvedUrl = new URL(cacheBustedPath, window.location.href).toString();
        console.log('[DEBUG] Attempting to fetch', cacheBustedPath, '->', resolvedUrl);
        dbReq = await fetch(cacheBustedPath);
        console.log('[DEBUG] Fetch response for', cacheBustedPath + ':', dbReq);
        if (dbReq.ok) {
          dbPathUsed = dbPath;
          break;
        }
      } catch (e) {
        console.error('[ERROR] Exception fetching', dbPath, e);
      }
    }
    if (!dbReq || !dbReq.ok) {
      console.error('[ERROR] Failed to fetch tradingcopilot.db from all tried paths. Last status:', dbReq?.status, dbReq?.statusText);
      throw new Error('Failed to fetch tradingcopilot.db');
    }
    const dbBuffer = await dbReq.arrayBuffer();
    console.log('[DEBUG] DB file loaded from', dbPathUsed, ', initializing sql.js...');
    // Initialize sql.js
    const SQL = await window.initSqlJs({ locateFile: file => `https://cdn.jsdelivr.net/npm/sql.js@1.8.0/dist/${file}` });
    const db = new SQL.Database(new Uint8Array(dbBuffer));
    console.log('[DEBUG] SQL.js initialized, DB instance created:', db);
    // Query the symbols table
    let symbolsData = [];
    try {
      const res = db.exec('SELECT symbol, description FROM symbols');
      console.log('[DEBUG] symbols table query result:', res);
      if (res.length > 0) {
        const cols = res[0].columns;
        const values = res[0].values;
        symbolsData = values.map(row => {
          const obj = {};
          cols.forEach((col, i) => { obj[col] = row[i]; });
          return obj;
        });
        console.log('[DEBUG] symbolsData array:', symbolsData);
      } else {
        console.warn('[DEBUG] symbols table query returned no results');
      }
    } catch (e) {
      console.error('[DEBUG] Error querying symbols table:', e);
      throw new Error('Failed to query symbols table');
    }
    // Prepare symbol list and UI
    const symbols = symbolsData.map(obj => obj.symbol);
    console.log('[DEBUG] symbols array:', symbols);
    window.SYMBOLS = symbols;
    INSTRUMENTS = buildInstruments(symbols);
    console.log('[DEBUG] INSTRUMENTS object:', INSTRUMENTS);
    initStateObjects(symbols);
    const restoreSymbol = symbols.includes(pendingDatasetSymbol) ? pendingDatasetSymbol : '';

    // Populate symbol selector
    const select = document.getElementById('symbolSelect');
    select.innerHTML = '';
    select.disabled = true;

    const placeholderOpt = document.createElement('option');
    placeholderOpt.value = '';
    placeholderOpt.textContent = 'Select...';
    select.appendChild(placeholderOpt);

    [...symbolsData].sort((a, b) => a.symbol.localeCompare(b.symbol)).forEach(obj => {
      const opt = document.createElement('option');
      opt.value = obj.symbol;
      opt.textContent = obj.description ? `${obj.symbol} - ${obj.description}` : obj.symbol;
      select.appendChild(opt);
    });
    console.log('[DEBUG] symbolSelect options populated:', select.innerHTML);
    select.value = restoreSymbol;
    // Wait for loaded to be initialized, then enable and attach event (robust)
    function enableDropdownWhenReady() {
      if (typeof loaded !== 'undefined' && loaded) {
        // Remove all previous event listeners by replacing the element
        const oldSelect = select;
        const newSelect = oldSelect.cloneNode(true);
        oldSelect.parentNode.replaceChild(newSelect, oldSelect);
        newSelect.disabled = false;
        // Debounce handler to avoid slow UI and race conditions
        let debounceTimer = null;
        newSelect.addEventListener('change', function() {
          if (debounceTimer) clearTimeout(debounceTimer);
          const value = this.value;
          debounceTimer = setTimeout(() => {
            handleSymbolSelect(value, db);
          }, 100); // 100ms debounce
        });
        if (restoreSymbol) {
          newSelect.value = restoreSymbol;
          setTimeout(() => handleSymbolSelect(restoreSymbol, db), 0);
        }
        console.log('[Dropdown] Dropdown enabled and event attached. Ready for user interaction.');
      } else {
        setTimeout(enableDropdownWhenReady, 50);
      }
    }
    enableDropdownWhenReady();
    buildSymbolSwitcher(symbols);
    // Save db instance for later use
    window._SQL_DB = db;
    // Reset active selection so re-selecting the same symbol after a dataset
    // switch doesn't hit the early-exit guard in handleSymbolSelect.
    activeSym = '';
    pendingDatasetSymbol = '';
    console.log('[DEBUG] loadSymbolsAndInit complete');
  }



  console.log('[DEBUG] After DOMContentLoaded event handler registration');

  const DEFAULT_INITIAL_CAPITAL = 1000;
  const PAPER_INITIAL_CAPITAL = 100000;

  function getDatasetInitialCapital() {
    return activeDataset === 'paper' ? PAPER_INITIAL_CAPITAL : DEFAULT_INITIAL_CAPITAL;
  }

  function normalizeBeginningEquity(beginEq) {
    if (!Number.isFinite(beginEq) || beginEq <= 0) return getDatasetInitialCapital();
    // Paper trading baseline should reflect the funded paper account.
    if (activeDataset === 'paper' && beginEq < 10000) return PAPER_INITIAL_CAPITAL;
    return beginEq;
  }

  function getInitialCapitalFromRows(rows) {
    if (!rows || !rows.length) return getDatasetInitialCapital();
    if (rows[0]._summary) {
      const s = rows[0]._summary || {};
      const beginEq = Number(s.beginning_equity);
      return normalizeBeginningEquity(beginEq);
    }
    const first = rows[0] || {};
    const eq = Number(first.equity);
    const pnl = Number(first.dollar_pnl);
    if (Number.isFinite(eq) && Number.isFinite(pnl)) {
      const beginEq = eq - pnl;
      if (Number.isFinite(beginEq) && beginEq > 0) return normalizeBeginningEquity(beginEq);
    }
    return getDatasetInitialCapital();
  }

  function getSymbolInitialCapital(sym) {
    const byVersion = loaded?.[sym] || {};
    for (const rows of Object.values(byVersion)) {
      if (rows && rows.length) return getInitialCapitalFromRows(rows);
    }
    return getDatasetInitialCapital();
  }

  function getActiveRows() {
    return activeTab === 'all'
      ? Object.values(loaded[activeSym] || {}).flat()
      : (loaded[activeSym]?.[activeTab] || []);
  }

  function getSelectedBacktestVariant(sym, ver) {
    return backtestSelections[sym]?.[ver] || 'main';
  }

  function getVersionLabel(sym, ver) {
    const cfg = INSTRUMENTS[sym].versions[ver];
    if (activeMode !== 'backtest' || !cfg.backtestVariants) return cfg.label;
    const variant = cfg.backtestVariants[getSelectedBacktestVariant(sym, ver)];
    return variant && variant.label !== 'Main' ? `${cfg.label} - ${variant.label}` : cfg.label;
  }

  function updateDatasetSwitcher() {
    const wrap = document.getElementById('datasetSwitcher');
    const v1Select = document.getElementById('v1DatasetSelect');
    const v2Select = document.getElementById('v2DatasetSelect');
    // Only show for the currently selected symbol if it supports backtestVariants
    const hasVariants = INSTRUMENTS[activeSym] && (
      (INSTRUMENTS[activeSym].versions['v1'] && INSTRUMENTS[activeSym].versions['v1'].backtestVariants) ||
      (INSTRUMENTS[activeSym].versions['v2'] && INSTRUMENTS[activeSym].versions['v2'].backtestVariants)
    );
    const show = activeMode === 'backtest' && hasVariants;
    if (wrap) wrap.style.display = show ? 'flex' : 'none';
    if (show) {
      if (v1Select && INSTRUMENTS[activeSym].versions['v1'] && INSTRUMENTS[activeSym].versions['v1'].backtestVariants) {
        v1Select.value = getSelectedBacktestVariant(activeSym, 'v1');
      }
      if (v2Select && INSTRUMENTS[activeSym].versions['v2'] && INSTRUMENTS[activeSym].versions['v2'].backtestVariants) {
        v2Select.value = getSelectedBacktestVariant(activeSym, 'v2');
      }
    }
  }
const fmt$   = n => (n>=0?'+$':'-$') + Math.abs(n).toFixed(2);
const fmtPct = n => (n>=0?'+':'') + n.toFixed(2) + '%';
const clsVal = n => n>0 ? 'positive' : n<0 ? 'negative' : 'neutral';
const fmtPF  = (pf, digits = 2) => Number.isFinite(pf) ? pf.toFixed(digits) : 'N/A';
function fmtDate(s) {
  if (!s) return '-';
  const d = new Date(s.replace(' ','T'));
  return isNaN(d) ? s : d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'2-digit'});
}
function resultTag(r) {
  if (!r) return '<span class="tag tag-other">-</span>';
  const u = r.toUpperCase();
  if (u==='TP') return '<span class="tag tag-tp">TP</span>';
  if (u==='SL') return '<span class="tag tag-sl">SL</span>';
  if (u==='MB') return '<span class="tag tag-mb">MB</span>';
  if (u.includes('TRAIL')) return '<span class="tag tag-trail">Trail</span>';
  return `<span class="tag tag-other">${r}</span>`;
}
function destroyChart(key) { if (charts[key]) { charts[key].destroy(); delete charts[key]; } }

function buildTabs() {
  const vers = INSTRUMENTS[activeSym].versions;
  const tabEl = document.getElementById('tabs');
  tabEl.innerHTML = '';
  const addBtn = (v, label, color) => {
    const btn = document.createElement('button');
    btn.className = 'tab' + (activeTab===v?' active':'');
    btn.dataset.v = v;
    btn.textContent = label;
    if (activeTab===v) btn.style.cssText = color
      ? `background:${color}22;border-color:${color};color:${color}`
      : 'background:#e6edf322;border-color:var(--text);color:var(--text)';
    btn.addEventListener('click', () => { activeTab = v; tradeTablePage = 1; txPage = 1; buildTabs(); render(); });
    tabEl.appendChild(btn);
  };
  addBtn('all','All Versions',null);
  for (const [vk, cfg] of Object.entries(vers)) addBtn(vk, getVersionLabel(activeSym, vk), cfg.color);

  const rerunBtnId = 'rerunWorkflowBtn';
  let rerunBtn = document.getElementById(rerunBtnId);
  const shouldShowBacktest = activeTab !== 'all' && activeDataset === 'backtest';
  const shouldShowPaper = activeTab !== 'all' && activeDataset === 'paper' && PAPER_TRADING_SUPPORTED_VERSIONS.has(activeTab);
  const shouldShowLive = activeTab !== 'all' && activeDataset === 'live' && LIVE_TRADING_SUPPORTED_VERSIONS.has(activeTab);
  if (shouldShowBacktest || shouldShowPaper || shouldShowLive) {
    if (!rerunBtn) {
      rerunBtn = document.createElement('button');
      rerunBtn.id = rerunBtnId;
      rerunBtn.style = 'margin-left:16px;padding:6px 18px;border-radius:6px;border:1px solid var(--accent);background:var(--accent);color:#fff;font-size:13px;font-weight:600;cursor:pointer;';
      tabEl.appendChild(rerunBtn);
    }
    rerunBtn.textContent = shouldShowBacktest
      ? 'Rerun Backtest'
      : (shouldShowPaper ? 'Rerun Paper Trading' : 'Rerun Live Trading');
    rerunBtn.onclick = function() {
      if (shouldShowBacktest) rerunBacktest(activeSym, activeTab);
      else if (shouldShowPaper) rerunPaperTrading(activeSym, activeTab);
      else rerunLiveTrading(activeSym, activeTab);
    };
    tabEl.appendChild(rerunBtn);
    rerunBtn.style.display = '';
  } else if (rerunBtn) {
    rerunBtn.style.display = 'none';
  }
}
function openWorkflowIssue(workflowType, symbol, version) {
  const sym = symbol.toUpperCase();
  const ver = version.toUpperCase();
  const isPaper = workflowType === 'paper';
  const isLive = workflowType === 'live';
  const workflowLabel = isLive ? 'Live Trading' : (isPaper ? 'Paper Trading' : 'Backtest');
  const issueTitle = encodeURIComponent(`Rerun ${workflowLabel}: ${sym} ${ver}`);
  const issueBody = encodeURIComponent(
    `Please rerun ${isLive ? 'live trading' : (isPaper ? 'paper trading' : 'the backtest')} for ${sym} version ${ver}.\n\n_This request was generated from the dashboard UI._`
  );
  const url = `https://github.com/rcaldwell67/pinescripts/issues/new?title=${issueTitle}&body=${issueBody}`;
  window.open(url, '_blank');
  updateWorkflowStatus(`${workflowLabel} rerun requested for ${sym} ${ver}. Submit the opened GitHub issue form to start the workflow.`, '#58a6ff');
}

function rerunBacktest(symbol, version) {
  openWorkflowIssue('backtest', symbol, version);
}

function rerunPaperTrading(symbol, version) {
  openWorkflowIssue('paper', symbol, version);
}

function rerunLiveTrading(symbol, version) {
  openWorkflowIssue('live', symbol, version);
}

function updateWorkflowStatus(msg, color) {
  const el = document.getElementById('workflowStatus');
  el.textContent = msg;
  if (color) el.style.color = color;
}

async function pollWorkflowStatus(issueNumber, sym, ver, workflowName = 'Rerun Backtest', workflowLabel = 'Backtest') {
  updateWorkflowStatus(`${workflowLabel} workflow: polling status...`, '#58a6ff');
  const owner = 'rcaldwell67';
  const repo = 'pinescripts';
  let pollCount = 0;
  const maxPolls = 30; // ~5 min
  const pollInterval = 10000; // 10s
  async function check() {
    pollCount++;
    // Fetch workflow runs for this issue
    const apiUrl = `https://api.github.com/repos/${owner}/${repo}/actions/runs?event=issues`;
    try {
      const resp = await fetch(apiUrl);
      const data = await resp.json();
      // Find the latest workflow run for this issue
      const runs = (data.workflow_runs || []).filter(run =>
        run.name && run.name.includes(workflowName) &&
        run.head_commit && run.head_commit.message &&
        run.head_commit.message.includes(`#${issueNumber}`)
      );
      const latest = runs[0];
      if (latest) {
        if (latest.status === 'completed') {
          if (latest.conclusion === 'success') {
            updateWorkflowStatus(`${workflowLabel} workflow: Success!`, '#2ea043');
          } else {
            updateWorkflowStatus(`${workflowLabel} workflow: Failed.`, '#ff4d4f');
          }
          return;
        } else {
          updateWorkflowStatus(`${workflowLabel} workflow: Running...`, '#58a6ff');
        }
      } else {
        updateWorkflowStatus(`${workflowLabel} workflow: Pending...`, '#ffa657');
      }
    } catch (e) {
      updateWorkflowStatus(`${workflowLabel} workflow status error.`, '#ff4d4f');
    }
    if (pollCount < maxPolls) setTimeout(check, pollInterval);
    else updateWorkflowStatus(`${workflowLabel} workflow: Timed out.`, '#ffa657');
  }
  check();
}
// Compute summary metrics from an array of individual trade rows.
// Returns null if no rows provided.
function calcMetrics(rows) {
  if (!rows || !rows.length) return null;
  const beginEqFromRows = getInitialCapitalFromRows(rows);
  if (rows[0]._summary) {
    const s = rows[0]._summary;
    const notes = (rows[0]._notes || '').toLowerCase();
    const n = Number(s.total_trades || 0);
    const wins = Number(s.winning_trades || 0);
    const losses = Number(s.losing_trades || Math.max(0, n - wins));
    const winRate = Number(s.win_rate || (n ? (wins / n * 100) : 0));
    const beginEq = Number(s.beginning_equity || beginEqFromRows || getDatasetInitialCapital());
    const finalEquity = Number(s.final_equity || beginEq);
    const netPnl = Number(s.total_pnl || (finalEquity - beginEq));
    const netPnlPct = Number(s.net_return_pct || (beginEq ? (netPnl / beginEq * 100) : 0));
    const maxDrawdownAbs = Number(s.max_drawdown || 0);
    const maxDD = beginEq ? (maxDrawdownAbs / beginEq * 100) : 0;
    const isShortOnly = notes.includes('short');
    const isLongOnly = notes.includes('long') && !isShortOnly;
    const longs = isShortOnly ? 0 : (isLongOnly ? n : Math.round(n / 2));
    const shorts = n - longs;
    const longWR = longs ? winRate : 0;
    const shortWR = shorts ? winRate : 0;
    const longPnl = longs ? netPnl : 0;
    const shortPnl = shorts ? netPnl : 0;
    const avgWin = wins ? Math.abs(netPnl) / wins : 0;
    const avgLoss = losses ? -(Math.abs(netPnl) / Math.max(losses, 1)) : 0;
    const pf = losses === 0 ? Infinity : Math.max(0, wins / losses);
    return {
      n,
      longs,
      shorts,
      winRate,
      tpCount: wins,
      slCount: losses,
      trailCount: 0,
      mbCount: 0,
      netPnl,
      netPnlPct,
      pf,
      maxDD,
      finalEquity,
      avgWin,
      avgLoss,
      longWR,
      shortWR,
      longPnl,
      shortPnl,
      beginEq,
    };
  }
  const n = rows.length;
  const wins = rows.filter(r => r.dollar_pnl > 0);
  const losses = rows.filter(r => r.dollar_pnl <= 0);
  const longs = rows.filter(r => r.direction === 'long').length;
  const shorts = rows.filter(r => r.direction === 'short').length;
  const tpCount = rows.filter(r => (r.result||'').toUpperCase() === 'TP').length;
  const slCount = rows.filter(r => (r.result||'').toUpperCase() === 'SL').length;
  const trailCount = rows.filter(r => { const u = (r.result||'').toUpperCase(); return u === 'TRAIL' || u === 'TRAILING'; }).length;
  const mbCount = rows.filter(r => (r.result||'').toUpperCase() === 'MB').length;
  const grossWin = wins.reduce((s, r) => s + r.dollar_pnl, 0);
  const grossLoss = Math.abs(losses.reduce((s, r) => s + r.dollar_pnl, 0));
  const netPnl = grossWin - grossLoss;
  const netPnlPct = beginEqFromRows ? (netPnl / beginEqFromRows) * 100 : 0;
  const pf = grossLoss === 0 ? Infinity : grossWin / grossLoss;
  const avgWin = wins.length ? grossWin / wins.length : 0;
  const avgLoss = losses.length ? -(grossLoss / losses.length) : 0;
  const winRate = (wins.length / n) * 100;
  let peak = beginEqFromRows, maxDD = 0;
  for (const r of rows) {
    if (r.equity > peak) peak = r.equity;
    const dd = peak > 0 ? (peak - r.equity) / peak * 100 : 0;
    if (dd > maxDD) maxDD = dd;
  }
  const finalEquity = rows[rows.length - 1].equity;
  const longRows = rows.filter(r => r.direction === 'long');
  const shortRows = rows.filter(r => r.direction === 'short');
  const longWR = longRows.length ? longRows.filter(r => r.dollar_pnl > 0).length / longRows.length * 100 : 0;
  const shortWR = shortRows.length ? shortRows.filter(r => r.dollar_pnl > 0).length / shortRows.length * 100 : 0;
  const longPnl = longRows.reduce((s, r) => s + r.dollar_pnl, 0);
  const shortPnl = shortRows.reduce((s, r) => s + r.dollar_pnl, 0);
  return { n, longs, shorts, winRate, tpCount, slCount, trailCount, mbCount, netPnl, netPnlPct, pf, maxDD, finalEquity, avgWin, avgLoss, longWR, shortWR, longPnl, shortPnl, beginEq: beginEqFromRows };
}

// No mode-toggle buttons exist in the current UI; this is a no-op placeholder.
function updateModeButtonStates() {}

function renderCards(rows) {
  const cardEl = document.getElementById('cards');
  const vers = INSTRUMENTS[activeSym].versions;
  if (activeTab === 'all') {
    cardEl.innerHTML = Object.entries(vers).map(([v,cfg])=>{
      const r = loaded[activeSym][v];
      if (!r?.length) return `<div class="card" style="border-top:2px solid ${cfg.color};opacity:0.5">
        <div class="label">${getVersionLabel(activeSym, v)}</div>
        <div class="value neutral">-</div>
        <div class="sub">No data yet</div>
      </div>`;
      const m = calcMetrics(r);
      return `<div class="card" style="border-top:2px solid ${cfg.color}">
        <div class="label">${getVersionLabel(activeSym, v)}</div>
        <div class="value ${clsVal(m.netPnl)}">${fmtPct(m.netPnlPct)}</div>
        <div class="sub">WR ${m.winRate.toFixed(1)}% - PF ${fmtPF(m.pf, 2)} - ${m.n} trades</div>
      </div>`;
    }).join('');
    return;
  }
  const m = calcMetrics(rows);
  if (!m) { cardEl.innerHTML=''; return; }
  cardEl.innerHTML = `
    <div class="card"><div class="label">Total Trades</div><div class="value neutral">${m.n}</div><div class="sub">${m.longs}L / ${m.shorts}S</div></div>
    <div class="card"><div class="label">Win Rate</div><div class="value ${m.winRate>=60?'positive':m.winRate>=50?'neutral':'negative'}">${m.winRate.toFixed(1)}%</div><div class="sub">${m.tpCount} TP - ${m.slCount} SL - ${m.trailCount} Trail${m.mbCount?' - '+m.mbCount+' MB':''}</div></div>
    <div class="card"><div class="label">Net P&L</div><div class="value ${clsVal(m.netPnl)}">${fmt$(m.netPnl)}</div><div class="sub">${fmtPct(m.netPnlPct)} on $${m.beginEq.toLocaleString()}</div></div>
    <div class="card"><div class="label">Profit Factor</div><div class="value ${m.pf>=2?'positive':m.pf>=1?'neutral':'negative'}">${fmtPF(m.pf, 3)}</div><div class="sub">Gross Win / Gross Loss</div></div>
    <div class="card"><div class="label">Max Drawdown</div><div class="value ${m.maxDD<5?'positive':m.maxDD<15?'neutral':'negative'}">-${m.maxDD.toFixed(2)}%</div><div class="sub">Peak-to-trough</div></div>
    <div class="card"><div class="label">Final Equity</div><div class="value ${clsVal(m.finalEquity-m.beginEq)}">$${m.finalEquity.toFixed(2)}</div><div class="sub">Started $${m.beginEq.toLocaleString()}</div></div>`;
}

function renderEquityChart(rows) {
  destroyChart('equity');
  const ctx = document.getElementById('equityChart').getContext('2d');
  const legendEl = document.getElementById('equityLegend');
  legendEl.innerHTML = '';
  const vers = INSTRUMENTS[activeSym].versions;
  let datasets = [];
  if (activeTab === 'all') {
    for (const [v,cfg] of Object.entries(vers)) {
      const r = loaded[activeSym][v];
      if (!r?.length) continue;
      const pts = r.map(t=>({ x:new Date(t.entry_time.replace(' ','T')), y:t.equity }));
      const label = getVersionLabel(activeSym, v);
      legendEl.innerHTML += `<div class="legend-item"><div class="dot" style="background:${cfg.color}"></div>${label}</div>`;
      datasets.push({ label, data:pts, borderColor:cfg.color, backgroundColor:'transparent', borderWidth:2, pointRadius:3, tension:0.1 });
    }
  } else {
    const cfg = vers[activeTab];
    const pts = rows.map(r=>({ x:new Date(r.entry_time.replace(' ','T')), y:r.equity }));
    const grad = ctx.createLinearGradient(0,0,0,300);
    grad.addColorStop(0, cfg.color+'33'); grad.addColorStop(1,'transparent');
    const label = getVersionLabel(activeSym, activeTab);
    legendEl.innerHTML = `<div class="legend-item"><div class="dot" style="background:${cfg.color}"></div>${label}</div>`;
    datasets.push({ label, data:pts, borderColor:cfg.color, backgroundColor:grad, borderWidth:2, fill:true, pointRadius:3, tension:0.1 });
  }
  const allPts = datasets.flatMap(d=>d.data);
  if (allPts.length) {
    const baselineCapital = activeTab === 'all' ? getSymbolInitialCapital(activeSym) : (calcMetrics(rows)?.beginEq || getDatasetInitialCapital());
    const minX = allPts.reduce((a,b)=>a.x<b.x?a:b,allPts[0]).x;
    const maxX = allPts.reduce((a,b)=>a.x>b.x?a:b,allPts[0]).x;
    datasets.push({ label:'Baseline', data:[{x:minX,y:baselineCapital},{x:maxX,y:baselineCapital}], borderColor:'#30363d', borderWidth:1, borderDash:[4,4], pointRadius:0 });
  }
  charts.equity = new Chart(ctx, {
    type:'line', data:{ datasets },
    options:{ animation:false, responsive:true, maintainAspectRatio:true,
      interaction:{ mode:'nearest', intersect:false },
      scales:{ x:{type:'time',time:{unit:'month'},grid:{color:'#21262d'},ticks:{color:'#8b949e'}}, y:{grid:{color:'#21262d'},ticks:{color:'#8b949e',callback:v=>'$'+v.toLocaleString()}} },
      plugins:{ legend:{display:false}, tooltip:{ callbacks:{ label:c=>` ${c.dataset.label}: $${c.parsed.y.toFixed(2)}` } } } }
  });
}

function renderOutcomeChart(rows) {
  destroyChart('outcome');
  const ctx = document.getElementById('outcomeChart').getContext('2d');
  const legendEl = document.getElementById('outcomeLegend');
  const all = activeTab==='all' ? Object.values(loaded[activeSym]).flat() : rows;
  const tp=all.filter(r=>r.result==='TP').length, sl=all.filter(r=>r.result==='SL').length;
  const trail=all.filter(r=>r.result==='TRAIL'||r.result==='TRAILING').length, mb=all.filter(r=>r.result==='MB').length;
  const other=all.length-tp-sl-trail-mb;
  const labels=['TP','SL','Trail'], vals=[tp,sl,trail], colors=['#3fb950','#f85149','#ffa657'];
  if (mb>0)    { labels.push('MB');    vals.push(mb);    colors.push('#d29922'); }
  if (other>0) { labels.push('Other'); vals.push(other); colors.push('#8b949e'); }
  legendEl.innerHTML = labels.map((l,i)=>`<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--border)"><span style="color:${colors[i]}">${l}</span><span style="font-weight:600">${vals[i]}</span></div>`).join('');
  charts.outcome = new Chart(ctx, {
    type:'doughnut', data:{ labels, datasets:[{ data:vals, backgroundColor:colors.map(c=>c+'44'), borderColor:colors, borderWidth:1.5 }] },
    options:{ animation:false, responsive:true, cutout:'65%', plugins:{ legend:{display:false}, tooltip:{ callbacks:{ label:c=>` ${c.label}: ${c.parsed} (${all.length?Math.round(c.parsed/all.length*100):0}%)` } } } }
  });
}

function renderDirectionChart(rows) {
  destroyChart('direction');
  const ctx = document.getElementById('directionChart').getContext('2d');
  const vers = INSTRUMENTS[activeSym].versions;
  if (activeTab !== 'all') {
    document.getElementById('dirChartTitle').textContent = 'P&L by Direction';
    const m = calcMetrics(rows); if (!m) return;
    charts.direction = new Chart(ctx, {
      type:'bar', data:{ labels:['Longs','Shorts'], datasets:[
        { label:'Win Rate %', data:[m.longWR,m.shortWR], backgroundColor:['#58a6ff44','#bc8cff44'], borderColor:['#58a6ff','#bc8cff'], borderWidth:1.5, yAxisID:'wr' },
        { label:'Net P&L $',  data:[m.longPnl,m.shortPnl], backgroundColor:['#3fb95033','#ffa65733'], borderColor:['#3fb950','#ffa657'], borderWidth:1.5, yAxisID:'pnl' },
      ]},
      options:{ animation:false, responsive:true, scales:{
        wr: {type:'linear',position:'left', grid:{color:'#21262d'},ticks:{color:'#8b949e',callback:v=>v.toFixed(0)+'%'}},
        pnl:{type:'linear',position:'right',grid:{drawOnChartArea:false},ticks:{color:'#8b949e',callback:v=>v.toFixed(1)+'%'}},
        x:{ticks:{color:'#8b949e'},grid:{color:'#21262d'}}
      }, plugins:{legend:{labels:{color:'#8b949e',font:{size:11}}}} }
    });
  } else {
    document.getElementById('dirChartTitle').textContent = 'Return by Version';
    const vkeys=Object.keys(vers).filter(v=>loaded[activeSym][v]?.length);
    const labels=vkeys.map(v=>vers[v].tf), wrs=vkeys.map(v=>calcMetrics(loaded[activeSym][v])?.winRate??0);
    const pnls=vkeys.map(v=>calcMetrics(loaded[activeSym][v])?.netPnlPct??0), colors=vkeys.map(v=>vers[v].color);
    charts.direction = new Chart(ctx, {
      type:'bar', data:{ labels, datasets:[
        { label:'Win Rate %', data:wrs,  backgroundColor:colors.map(c=>c+'44'), borderColor:colors, borderWidth:1.5, yAxisID:'wr' },
        { label:'Return %',   data:pnls, backgroundColor:pnls.map(v=>v>=0?'#3fb95022':'#f8514922'), borderColor:pnls.map(v=>v>=0?'#3fb950':'#f85149'), borderWidth:1.5, yAxisID:'pnl' },
      ]},
      options:{ animation:false, responsive:true, scales:{
        wr: {type:'linear',position:'left', grid:{color:'#21262d'},ticks:{color:'#8b949e',callback:v=>v.toFixed(0)+'%'}},
        pnl:{type:'linear',position:'right',grid:{drawOnChartArea:false},ticks:{color:'#8b949e',callback:v=>v.toFixed(1)+'%'}},
        x:{ticks:{color:'#8b949e'},grid:{color:'#21262d'}}
      }, plugins:{legend:{labels:{color:'#8b949e',font:{size:11}}}} }
    });
  }
}

function renderMonthlyChart(rows) {
  destroyChart('monthly');
  const ctx=document.getElementById('monthlyChart').getContext('2d');
  const src=activeTab==='all'?Object.values(loaded[activeSym]).flat():rows;
  const monthly={};
  for (const r of src) {
    if (!r.entry_time) continue;
    const d=new Date(r.entry_time.replace(' ','T')); if (isNaN(d)) continue;
    const key=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
    monthly[key]=(monthly[key]||0)+r.dollar_pnl;
  }
  const sorted=Object.keys(monthly).sort(), vals=sorted.map(k=>monthly[k]);
  charts.monthly = new Chart(ctx, {
    type:'bar', data:{ labels:sorted, datasets:[{ label:'Monthly P&L ($)', data:vals,
      backgroundColor:vals.map(v=>v>=0?'#3fb95066':'#f8514966'), borderColor:vals.map(v=>v>=0?'#3fb950':'#f85149'), borderWidth:1.5 }] },
    options:{ animation:false, responsive:true, scales:{
      x:{ticks:{color:'#8b949e',maxRotation:45,font:{size:10}},grid:{color:'#21262d'}},
      y:{grid:{color:'#21262d'},ticks:{color:'#8b949e',callback:v=>'$'+v.toFixed(0)}}
    }, plugins:{legend:{display:false}} }
  });
}

function renderYearChart() {
  destroyChart('year');
  const vers=INSTRUMENTS[activeSym].versions;
  const verKey=activeTab!=='all'
    ?(vers[activeTab]?.hasYear?activeTab:null)
    :Object.keys(vers).find(v=>vers[v].hasYear&&loaded[activeSym][v]?.length);
  if (!verKey) return;
  const rows=loaded[activeSym][verKey], cfg=vers[verKey];
  document.getElementById('yearChartTitle').textContent=`Year-by-Year - ${getVersionLabel(activeSym, verKey)}`;
  const years={};
  for (const r of rows) {
    const y=r.year||new Date(r.entry_time.replace(' ','T')).getFullYear();
    if (!years[y]) years[y]={pnl:0,n:0,wins:0};
    years[y].pnl+=r.dollar_pnl; years[y].n++;
    if (r.dollar_pnl>0) years[y].wins++;
  }
  const sorted=Object.keys(years).sort(), pnls=sorted.map(y=>years[y].pnl), wrs=sorted.map(y=>years[y].wins/years[y].n*100);
  const ctx=document.getElementById('yearChart').getContext('2d');
  charts.year = new Chart(ctx, {
    type:'bar', data:{ labels:sorted, datasets:[
      { label:'Net P&L ($)', data:pnls, backgroundColor:pnls.map(v=>v>=0?cfg.color+'55':'#f8514966'), borderColor:pnls.map(v=>v>=0?cfg.color:'#f85149'), borderWidth:1.5, yAxisID:'pnl' },
      { label:'Win Rate %',  data:wrs, backgroundColor:'transparent', borderColor:'#ffa657', borderWidth:2, type:'line', yAxisID:'wr', pointRadius:5 },
    ]},
    options:{ animation:false, responsive:true, scales:{
      pnl:{type:'linear',position:'left', grid:{color:'#21262d'},ticks:{color:'#8b949e',callback:v=>'$'+v.toFixed(0)}},
      wr: {type:'linear',position:'right',min:0,max:100,grid:{drawOnChartArea:false},ticks:{color:'#8b949e',callback:v=>v+'%'}},
      x:{ticks:{color:'#8b949e'},grid:{color:'#21262d'}}
    }, plugins:{legend:{labels:{color:'#8b949e',font:{size:11}}}} }
  });
}

function renderTradeTable(rows) {
  const wrap = document.getElementById('tradeTableWrap');
  if (!rows?.length) { wrap.innerHTML = '<div class="empty">No data</div>'; return; }
  const showVer = activeTab === 'all';
  const vers = INSTRUMENTS[activeSym].versions;
  const sorted = rows.slice().sort((a, b) => {
    const ta = a.entry_time ? new Date(a.entry_time.replace(' ','T')).getTime() : 0;
    const tb = b.entry_time ? new Date(b.entry_time.replace(' ','T')).getTime() : 0;
    return tb - ta;
  });
  const total = sorted.length;
  const totalPages = Math.max(1, Math.ceil(total / tradePageSize));
  if (tradeTablePage > totalPages) tradeTablePage = totalPages;
  const start = (tradeTablePage - 1) * tradePageSize;
  const paged = sorted.slice(start, start + tradePageSize);
  const end = start + paged.length;
  const pagCtrl = total > tradePageSize ? `<div class="pagination">
    <span class="pg-info">${start+1}-${end} of ${total} trades</span>
    <div class="pg-btns">
      <button class="pg-btn" ${tradeTablePage<=1?'disabled':''} onclick="tradeTablePage=1;renderTradeTable(getActiveRows())"><<</button>
      <button class="pg-btn" ${tradeTablePage<=1?'disabled':''} onclick="tradeTablePage--;renderTradeTable(getActiveRows())"><</button>
      <span class="pg-info" style="padding:0 8px">Page ${tradeTablePage} / ${totalPages}</span>
      <button class="pg-btn" ${tradeTablePage>=totalPages?'disabled':''} onclick="tradeTablePage++;renderTradeTable(getActiveRows())">></button>
      <button class="pg-btn" ${tradeTablePage>=totalPages?'disabled':''} onclick="tradeTablePage=${totalPages};renderTradeTable(getActiveRows())">>></button>
    </div>
  </div>` : '';
  wrap.innerHTML = `<table><thead><tr>
    ${showVer ? '<th scope="col">Ver</th>' : ''}
    <th scope="col">Entry</th><th scope="col">Exit</th><th scope="col">Dir</th><th scope="col">Entry $</th><th scope="col">Exit $</th><th scope="col">P&L</th><th scope="col">Result</th><th scope="col">Equity</th>
  </tr></thead><tbody>${paged.map(r => {
    const dirTag = r.direction === 'long' ? 'tag-long' : 'tag-short';
    const cfg = vers[r.version];
    const ep = r.entry_price < 100 ? '$' + r.entry_price?.toFixed(4) : '$' + r.entry_price?.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
    const xp = r.exit_price  < 100 ? '$' + r.exit_price?.toFixed(4)  : '$' + r.exit_price?.toLocaleString('en-US',  {minimumFractionDigits:2, maximumFractionDigits:2});
    return `<tr>
      ${showVer ? `<td><span class="pill" style="background:${cfg.color}22;color:${cfg.color};border-color:${cfg.color}">${cfg.tf}</span></td>` : ''}
      <td>${fmtDate(r.entry_time)}</td><td>${fmtDate(r.exit_time)}</td>
      <td><span class="tag ${dirTag}">${r.direction || '-'}</span></td>
      <td>${ep}</td><td>${xp}</td>
      <td class="${clsVal(r.dollar_pnl)}">${fmt$(r.dollar_pnl)}</td>
      <td>${resultTag(r.result)}</td>
      <td>$${r.equity?.toFixed(2)}</td>
    </tr>`;
  }).join('')}</tbody></table>${pagCtrl}`;
}

function parseDashboardTimeValue(value) {
  if (!value) return 0;
  const ms = new Date(String(value).replace(' ', 'T')).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

function getAllSymbolsCumulativeEquity() {
  const db = window._SQL_DB;
  if (!db) return null;
  const modeFilter = activeDataset === 'backtest' ? 'backtest' : (activeDataset === 'paper' ? 'paper' : 'live');
  const rowsBySymbolVersion = new Map();
  try {
    const stmt = db.prepare('SELECT symbol, version, equity, dollar_pnl, direction, result, entry_time, exit_time FROM trades WHERE mode = ?');
    stmt.bind([modeFilter]);
    while (stmt.step()) {
      const r = stmt.getAsObject();
      const symKey = getNormalizedSymbolKey(r.symbol || '');
      const verKey = String(r.version || 'v1').toLowerCase();
      if (!symKey) continue;
      const key = `${symKey}|${verKey}`;
      if (!rowsBySymbolVersion.has(key)) rowsBySymbolVersion.set(key, []);
      rowsBySymbolVersion.get(key).push({
        symbol: symKey,
        version: verKey,
        equity: Number(r.equity),
        dollar_pnl: Number(r.dollar_pnl),
        direction: r.direction,
        result: r.result,
        entry_time: r.entry_time,
        exit_time: r.exit_time,
      });
    }
    stmt.free();
  } catch (e) {
    console.error('Error computing all-symbol cumulative equity:', e);
    return null;
  }

  const perSymbol = new Map();
  for (const groupedRows of rowsBySymbolVersion.values()) {
    if (!groupedRows.length) continue;
    groupedRows.sort((a, b) => parseDashboardTimeValue(a.entry_time || a.exit_time) - parseDashboardTimeValue(b.entry_time || b.exit_time));
    const metrics = calcMetrics(groupedRows);
    if (!metrics) continue;
    const symbolKey = groupedRows[0].symbol;
    if (!perSymbol.has(symbolKey)) {
      perSymbol.set(symbolKey, { startCapital: metrics.beginEq, totalNet: 0 });
    }
    const current = perSymbol.get(symbolKey);
    current.totalNet += (metrics.finalEquity - metrics.beginEq);
    if ((!Number.isFinite(current.startCapital) || current.startCapital <= 0) && Number.isFinite(metrics.beginEq) && metrics.beginEq > 0) {
      current.startCapital = metrics.beginEq;
    }
  }

  if (!perSymbol.size) return null;
  let baseline = 0;
  let equity = 0;
  for (const item of perSymbol.values()) {
    const start = Number.isFinite(item.startCapital) && item.startCapital > 0 ? item.startCapital : getDatasetInitialCapital();
    baseline += start;
    equity += (start + item.totalNet);
  }
  return { equity, baseline };
}

function buildTransactions() {
  const txns = [];
  const symData = INSTRUMENTS[activeSym];
  for (const [ver, cfg] of Object.entries(symData.versions)) {
    const rows = loaded[activeSym][ver] || [];
    let prevEquity = getInitialCapitalFromRows(rows);
    for (const r of rows) {
      const begEquity = prevEquity;
      const isLong = r.direction === 'long';
      txns.push({ time:r.entry_time, sym:activeSym, ver, cfg, symLabel:symData.label,
        action: isLong?'BUY':'SELL', price:r.entry_price, type:'Open',
        direction:r.direction, pnl:null, result:null, begEquity, endEquity:null });
      txns.push({ time:r.exit_time, sym:activeSym, ver, cfg, symLabel:symData.label,
        action: isLong?'SELL':'BUY', price:r.exit_price, type:'Close',
        direction:r.direction, pnl:r.dollar_pnl, result:r.result, begEquity, endEquity:r.equity });
      prevEquity = r.equity;
    }
  }
  txns.sort((a,b) => new Date(b.time?.replace(' ','T')||0) - new Date(a.time?.replace(' ','T')||0));
  return txns;
}

function updateVerFilter() {
  const vers = INSTRUMENTS[activeSym].versions;

  // Version filter
  const vsel = document.getElementById('txVerFilter');
  const vcur = vsel.value;
  vsel.innerHTML = '<option value="all">All Versions</option>';
  for (const [v, cfg] of Object.entries(vers)) {
    const opt = document.createElement('option');
    opt.value = v; opt.textContent = getVersionLabel(activeSym, v);
    vsel.appendChild(opt);
  }
  if ([...vsel.options].some(o=>o.value===vcur)) vsel.value = vcur;

  // Timeframe filter: unique tf values in insertion order
  const tfsel = document.getElementById('txTfFilter');
  const tfcur = tfsel.value;
  const tfs = [...new Set(Object.values(vers).map(c => c.tf))];
  tfsel.innerHTML = '<option value="all">All Timeframes</option>';
  for (const tf of tfs) {
    const opt = document.createElement('option');
    opt.value = tf; opt.textContent = tf;
    tfsel.appendChild(opt);
  }
  if ([...tfsel.options].some(o=>o.value===tfcur)) tfsel.value = tfcur;
}

function resetTransactionFilters() {
  const ids = ['txVerFilter', 'txTfFilter', 'txActionFilter', 'txDirFilter', 'txTypeFilter'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = 'all';
  });
  txPage = 1;
}

function renderTransactionsTable() {
  updateVerFilter();
  const verF    = document.getElementById('txVerFilter').value;
  const tfF     = document.getElementById('txTfFilter').value;
  const actionF = document.getElementById('txActionFilter').value;
  const dirF    = document.getElementById('txDirFilter').value;
  const typeF   = document.getElementById('txTypeFilter').value;
  let txns = buildTransactions();
  if (verF    !== 'all') txns = txns.filter(t => t.ver === verF);
  if (tfF     !== 'all') txns = txns.filter(t => t.cfg.tf === tfF);
  if (actionF !== 'all') txns = txns.filter(t => t.action === actionF);
  if (dirF    !== 'all') txns = txns.filter(t => t.direction === dirF);
  if (typeF   !== 'all') txns = txns.filter(t => t.type === typeF);
  const total = txns.length;
  const countEl = document.getElementById('txCount');
  countEl.textContent = total ? total + ' transactions' : '';
  const wrap = document.getElementById('txTableWrap');
  if (!total) { wrap.innerHTML = '<div class="empty">No transactions match filters</div>'; return; }
  const totalPages = Math.max(1, Math.ceil(total / txPageSize));
  if (txPage > totalPages) txPage = totalPages;
  const start = (txPage - 1) * txPageSize;
  const paged = txns.slice(start, start + txPageSize);
  const end = start + paged.length;
  const pagCtrl = total > txPageSize ? `<div class="pagination">
    <span class="pg-info">${start+1}-${end} of ${total} transactions</span>
    <div class="pg-btns">
      <button class="pg-btn" ${txPage<=1?'disabled':''} onclick="txPage=1;renderTransactionsTable()"><<</button>
      <button class="pg-btn" ${txPage<=1?'disabled':''} onclick="txPage--;renderTransactionsTable()"><</button>
      <span class="pg-info" style="padding:0 8px">Page ${txPage} / ${totalPages}</span>
      <button class="pg-btn" ${txPage>=totalPages?'disabled':''} onclick="txPage++;renderTransactionsTable()">></button>
      <button class="pg-btn" ${txPage>=totalPages?'disabled':''} onclick="txPage=${totalPages};renderTransactionsTable()">>></button>
    </div>
  </div>` : '';
  const fmtEq = e => e==null||isNaN(e) ? '-' : '$'+e.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  wrap.innerHTML = `<table><thead><tr>
    <th scope="col">Date / Time</th><th scope="col">Version</th><th scope="col">Action</th><th scope="col">Type</th><th scope="col">Direction</th><th scope="col">Price</th><th scope="col">P&L</th><th scope="col">Beg. Bal</th><th scope="col">End Bal</th><th scope="col">Result</th>
  </tr></thead><tbody>${paged.map(t => {
    const fmtP = p => isNaN(p)?'-' : p<100?'$'+p.toFixed(4):'$'+p.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    const actionTag = t.action==='BUY'
      ? `<span class="tag tag-buy">BUY</span>`
      : `<span class="tag tag-sell">SELL</span>`;
    const typeTag = t.type==='Open'
      ? `<span class="tag tag-open">Open</span>`
      : `<span class="tag tag-close">Close</span>`;
    const dirTag = t.direction==='long'
      ? `<span class="tag tag-long">long</span>`
      : `<span class="tag tag-short">short</span>`;
    const pnlCell = t.pnl!=null ? `<span class="${clsVal(t.pnl)}">${fmt$(t.pnl)}</span>` : '<span style="color:var(--border)">-</span>';
    const begCell = `<span style="color:var(--muted)">${fmtEq(t.begEquity)}</span>`;
    const endCell = t.endEquity!=null
      ? `<span class="${clsVal(t.endEquity - t.begEquity)}">${fmtEq(t.endEquity)}</span>`
      : '<span style="color:var(--border)">-</span>';
    return `<tr>
      <td>${t.time||'-'}</td>
      <td><span class="pill" style="background:${t.cfg.color}22;color:${t.cfg.color};border-color:${t.cfg.color}">${t.cfg.tf}</span></td>
      <td>${actionTag}</td><td>${typeTag}</td><td>${dirTag}</td>
      <td>${fmtP(t.price)}</td><td>${pnlCell}</td><td>${begCell}</td><td>${endCell}</td><td>${t.result?resultTag(t.result):'<span style="color:var(--border)">-</span>'}</td>
    </tr>`;
  }).join('')}</tbody></table>${pagCtrl}`;
}

// Price Chart (Lightweight Charts)
const chartDataCache = {};
let lcChartInst = null;

// Single source of truth for chart data. Returns { bars, generated_at }.
// Queries the already-loaded sql.js DB instance (window._SQL_DB) — no extra
// HTTP request. Caches by sym; caller may bust cache by deleting chartDataCache[sym].
async function loadChartData(sym) {
  if (chartDataCache[sym]) return chartDataCache[sym];
  const db = window._SQL_DB;
  if (!db) throw new Error('DB not loaded');

  // Read generated_at from chart_meta
  let generated_at = null;
  try {
    const stmt = db.prepare('SELECT generated_at FROM chart_meta WHERE symbol = ?');
    stmt.bind([sym]);
    if (stmt.step()) generated_at = stmt.getAsObject().generated_at;
    stmt.free();
  } catch (e) { /* chart_meta may not exist in older DB snapshots */ }

  // Read bars from chart_data ordered by time
  const bars = [];
  try {
    const stmt = db.prepare('SELECT t, o, h, l, c, v FROM chart_data WHERE symbol = ? ORDER BY t ASC');
    stmt.bind([sym]);
    while (stmt.step()) {
      const r = stmt.getAsObject();
      bars.push({ t: r.t, o: r.o, h: r.h, l: r.l, c: r.c, v: r.v });
    }
    stmt.free();
  } catch (e) { /* chart_data may not exist in older DB snapshots */ }

  chartDataCache[sym] = { bars, generated_at };
  return chartDataCache[sym];
}

async function updateLastUpdated() {
  try {
    // Bust the cache so we always get the freshest timestamp
    delete chartDataCache[activeSym];
    const { bars, generated_at } = await loadChartData(activeSym);
    const refTime = generated_at ? new Date(generated_at)
                  : (bars.length ? new Date(bars[bars.length - 1].t * 1000) : null);
    if (refTime) {
      const diffMin = Math.round((Date.now() - refTime) / 60000);
      const timeStr = refTime.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' });
      const ageStr = diffMin < 60 ? `${diffMin}m ago` : diffMin < 1440 ? `${Math.round(diffMin / 60)}h ago` : `${Math.round(diffMin / 1440)}d ago`;
      document.getElementById('lastUpdated').textContent = `Updated: ${timeStr} (${ageStr})`;
    }
  } catch(e) { /* leave as-is */ }
}

function computeEMA(bars, period) {
  const k = 2 / (period + 1);
  const result = [];
  let ema = bars[0].c;
  for (let i = 0; i < bars.length; i++) {
    ema = bars[i].c * k + ema * (1 - k);
    if (i >= period - 1) result.push({ time: bars[i].t, value: parseFloat(ema.toFixed(6)) });
  }
  return result;
}

// Snap each marker's time to the nearest bar in barTimes (sorted ascending).
// Required because IEX data is sparse; trade entry/exit times often fall on
// 5-min boundaries that have no bar (no trades occurred on that candle).
function snapMarkersToBars(markers, barTimes) {
  if (!barTimes.length) return [];
  return markers.map(m => {
    // Binary search for first bar >= marker time
    let lo = 0, hi = barTimes.length - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (barTimes[mid] < m.time) lo = mid + 1; else hi = mid; }
    // Compare neighbour below (lo-1) and at/above (lo)
    const above = barTimes[lo];
    const below = lo > 0 ? barTimes[lo - 1] : above;
    const nearest = (Math.abs(above - m.time) <= Math.abs(below - m.time)) ? above : below;
    return nearest === m.time ? m : { ...m, time: nearest };
  });
}

function getPriceChartMarkers(sym, tab) {
  const vers = INSTRUMENTS[sym].versions;
  const markers = [];
  const versToShow = tab === 'all' ? Object.keys(vers) : [tab];
  for (const vk of versToShow) {
    const rows = loaded[sym][vk] || [];
    const cfg = vers[vk];
    for (const r of rows) {
      const entTs = r.entry_time ? Math.floor(new Date(r.entry_time.replace(' ','T')).getTime()/1000) : null;
      const exTs  = r.exit_time  ? Math.floor(new Date(r.exit_time.replace(' ','T')).getTime()/1000)  : null;
      if (entTs) markers.push({
        time: entTs,
        position: r.direction === 'long' ? 'belowBar' : 'aboveBar',
        color:    r.direction === 'long' ? '#3fb950'  : '#bc8cff',
        shape:    r.direction === 'long' ? 'arrowUp'  : 'arrowDown',
        text:     tab === 'all' ? cfg.tf : (r.direction === 'long' ? 'Long' : 'Short'),
        size: 0.8,
      });
      if (exTs) {
        const rc = (r.result||'').toUpperCase();
        let color = '#8b949e';
        if (rc === 'TP')              color = '#3fb950';
        else if (rc === 'SL')        color = '#f85149';
        else if (rc.includes('TRAIL')) color = '#ffa657';
        markers.push({
          time: exTs,
          position: r.direction === 'long' ? 'aboveBar' : 'belowBar',
          color, shape: 'circle',
          text: rc || 'Exit', size: 0.5,
        });
      }
    }
  }
  markers.sort((a,b) => a.time - b.time);
  // Deduplicate markers at same time (keep first)
  const seen = new Set();
  return markers.filter(m => { const k = m.time+'|'+m.position; if (seen.has(k)) return false; seen.add(k); return true; });
}

// Aggregate 5-min bars into coarser buckets (for 3M/6M/All views).
// Lightweight Charts has a hard minimum of 0.5px/bar, so a 1200px chart
// can only display ~2400 bars. Large datasets may require resampling.
// Solution: resample to ~30-min buckets for views with >1500 bars.
function resampleBars(bars, targetMaxBars) {
  if (bars.length <= targetMaxBars) return bars;
  const factor = Math.ceil(bars.length / targetMaxBars);
  const out = [];
  for (let i = 0; i < bars.length; i += factor) {
    const chunk = bars.slice(i, i + factor);
    out.push({
      t: chunk[0].t,
      o: chunk[0].o,
      h: Math.max(...chunk.map(b => b.h)),
      l: Math.min(...chunk.map(b => b.l)),
      c: chunk[chunk.length - 1].c,
      v: chunk.reduce((s, b) => s + b.v, 0),
    });
  }
  return out;
}

async function renderPriceChart() {
  const container = document.getElementById('lcChartContainer');
  if (!container) return;
  if (lcChartInst) { lcChartInst.remove(); lcChartInst = null; }
  container.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:16px 0;">Loading chart dataGǪ</div>';

  let bars;
  try { ({ bars } = await loadChartData(activeSym)); } catch(e) {
    container.innerHTML = `<div class="empty">Chart data unavailable: ${e.message}</div>`; return;
  }
  if (!bars?.length) { container.innerHTML = '<div class="empty">No bar data</div>'; return; }
  container.innerHTML = '';

  const rangeDays = parseInt(document.getElementById('chartRangeSelect')?.value || '180');
  const lastT  = bars[bars.length-1].t;
  const cutoff = rangeDays > 0 ? lastT - rangeDays * 86400 : 0;
  let visible = bars.filter(b => b.t >= cutoff);
  if (!visible.length) { container.innerHTML = '<div class="empty">No bars in selected range</div>'; return; }

  // Resample if too many bars for LC to display at minBarSpacing=0.5
  // Keep full-resolution for markers; use resampled for candles+EMA rendering
  const MAX_CANDLE_BARS = 1400;
  const displayBars = resampleBars(visible, MAX_CANDLE_BARS);

  try {
    // Use fixed width (container has explicit CSS height so clientWidth is valid)
    lcChartInst = LightweightCharts.createChart(container, {
      width:  container.clientWidth || 1200,
      height: 400,
      layout:  { background: { type: 'solid', color: '#161b22' }, textColor: '#8b949e' },
      grid:    { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#30363d' },
      timeScale: { borderColor: '#30363d', timeVisible: true, secondsVisible: false, rightOffset: 5 },
    });

    // Resize when container width changes
    new ResizeObserver(() => { if (lcChartInst) lcChartInst.applyOptions({ width: container.clientWidth }); }).observe(container);

    const candleSeries = lcChartInst.addCandlestickSeries({
      upColor:'#3fb950', downColor:'#f85149',
      borderUpColor:'#3fb950', borderDownColor:'#f85149',
      wickUpColor:'#3fb950', wickDownColor:'#f85149',
    });
    candleSeries.setData(displayBars.map(b => ({ time:b.t, open:b.o, high:b.h, low:b.l, close:b.c })));

    // Compute EMA from full-resolution bars, then filter/snap to displayBars timestamps
    const displayTimes = new Set(displayBars.map(b => b.t));
    const emaConfigs = [
      { period:21,  color:'#58a6ff' },
      { period:50,  color:'#ffa657' },
      { period:200, color:'#f85149' },
    ];
    for (const { period, color } of emaConfigs) {
      const allEma = computeEMA(bars, period);
      // Keep only EMA points whose time exists in displayBars
      const visEma = allEma.filter(p => p.time >= cutoff && displayTimes.has(p.time));
      if (!visEma.length) continue;
      const ls = lcChartInst.addLineSeries({ color, lineWidth:1, priceLineVisible:false, lastValueVisible:false });
      ls.setData(visEma);
    }

    // fitContent() fits exactly the loaded data with no empty space on the right.
    // Do NOT use scrollToRealTime(); that scrolls to wall-clock time, leaving
    // empty space after the last bar and pushing data off-screen to the left.
    lcChartInst.timeScale().fitContent();

    const barTimes = displayBars.map(b => b.t);
    const rawMarkers = getPriceChartMarkers(activeSym, activeTab).filter(m => m.time >= cutoff);
    if (rawMarkers.length) {
      const snapped = snapMarkersToBars(rawMarkers, barTimes);
      const seen2 = new Set();
      const deduped = snapped.filter(m => { const k = m.time+'|'+m.position; if (seen2.has(k)) return false; seen2.add(k); return true; });
      try { candleSeries.setMarkers(deduped); } catch(e) { console.warn('setMarkers failed:', e); }
    }
  } catch(e) {
    console.error('Price chart render error:', e);
    container.innerHTML = `<div class="empty">Chart render error: ${e.message}</div>`;
  }
}

document.getElementById('chartRangeBtns')?.addEventListener('click', e => {
  const btn = e.target.closest('.chart-range-btn');
  if (!btn) return;
  document.querySelectorAll('.chart-range-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('chartRangeSelect').value = btn.dataset.days;
  renderPriceChart();
});

function renderComparisonTable() {
  const el=document.getElementById('cmpTable');
  const vers=INSTRUMENTS[activeSym].versions;
  const vkeys=Object.keys(vers);
  const items=vkeys.map(v=>({ v, m: loaded[activeSym][v]?.length ? calcMetrics(loaded[activeSym][v]) : null, cfg:vers[v] }));
  const nd = '-';
  const rows=[
    ['Timeframe',       i=>i.cfg.tf],
    ['Trades',          i=>i.m ? i.m.n : nd],
    ['Win Rate',        i=>i.m ? i.m.winRate.toFixed(1)+'%' : nd],
    ['Net P&L',         i=>i.m ? fmt$(i.m.netPnl) : nd],
    ['Net Return',      i=>i.m ? fmtPct(i.m.netPnlPct) : nd],
    ['Profit Factor',   i=>i.m ? fmtPF(i.m.pf, 3) : nd],
    ['Max Drawdown',    i=>i.m ? '-'+i.m.maxDD.toFixed(2)+'%' : nd],
    ['Avg Win',         i=>i.m ? fmt$(i.m.avgWin) : nd],
    ['Avg Loss',        i=>i.m ? fmt$(i.m.avgLoss) : nd],
    ['Longs / Shorts',  i=>i.m ? `${i.m.longs} / ${i.m.shorts}` : nd],
    ['TP / SL / Trail', i=>i.m ? `${i.m.tpCount} / ${i.m.slCount} / ${i.m.trailCount}` : nd],
  ];
  el.innerHTML=`<thead><tr><th scope="col">Metric</th>${items.map(i=>`<th scope="col"><span class="pill" style="background:${i.cfg.color}22;color:${i.cfg.color};border-color:${i.cfg.color}">${getVersionLabel(activeSym, i.v)}</span></th>`).join('')}</tr></thead>
  <tbody>${rows.map(([label,fn])=>`<tr><td>${label}</td>${items.map(i=>`<td style="${!i.m&&label!=='Timeframe'?'opacity:0.4':''}">` + fn(i) + `</td>`).join('')}</tr>`).join('')}</tbody>`;
}

function updateBalanceBar(rows) {
  const beginEl = document.getElementById('beginningBalanceVal');
  const endEl   = document.getElementById('endingBalanceVal');
  const totalEl = document.getElementById('totalEquityVal');
  const totalAllEl = document.getElementById('totalEquityAllVal');
  const totalAllSymbolsEl = document.getElementById('totalEquityAllSymbolsVal');
  const vers = INSTRUMENTS[activeSym].versions;
  const startCapital = getSymbolInitialCapital(activeSym);
  const fmtBal = (n, el, baseline = startCapital) => {
    if (!el) return;
    el.textContent = '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    el.className = 'bal-value ' + (n > baseline ? 'positive' : n < baseline ? 'negative' : 'neutral');
  };

  fmtBal(startCapital, beginEl, startCapital);

  // Ending balance: only meaningful when a single version is selected
  if (!rows || !rows.length) {
    endEl.textContent = '-'; endEl.className = 'bal-value neutral';
  } else {
    const eq = rows[rows.length - 1].equity;
    isNaN(eq) ? (endEl.textContent = '-', endEl.className = 'bal-value neutral') : fmtBal(eq, endEl);
  }

  // Total equity: sum net profits from every loaded version + one start-capital base.
  const versionMetrics = Object.values(loaded[activeSym])
    .filter(v => v && v.length)
    .map(v => calcMetrics(v))
    .filter(Boolean);
  const totalNetProfit = versionMetrics.reduce((sum, m) => sum + (m.finalEquity - m.beginEq), 0);
  if (totalNetProfit === 0 && versionMetrics.length === 0) {
    totalEl.textContent = '-'; totalEl.className = 'bal-value neutral';
    if (totalAllEl) { totalAllEl.textContent = '-'; totalAllEl.className = 'bal-value neutral'; }
  } else {
    const cumulativeEquity = startCapital + totalNetProfit;
    fmtBal(cumulativeEquity, totalEl);
    fmtBal(cumulativeEquity, totalAllEl);
  }

  const allSymbolsTotals = getAllSymbolsCumulativeEquity();
  if (!totalAllSymbolsEl) return;
  if (!allSymbolsTotals || !Number.isFinite(allSymbolsTotals.equity)) {
    totalAllSymbolsEl.textContent = '-';
    totalAllSymbolsEl.className = 'bal-value neutral';
    return;
  }
  fmtBal(allSymbolsTotals.equity, totalAllSymbolsEl, allSymbolsTotals.baseline);
}

function render() {
  const vers=INSTRUMENTS[activeSym].versions;
  const rows=activeTab==='all'?Object.values(loaded[activeSym]).flat():(loaded[activeSym][activeTab]||[]);
  updateDatasetSwitcher();
  updateBalanceBar(activeTab === 'all' ? null : rows);
  renderCards(rows);
  renderEquityChart(rows);
  renderOutcomeChart(rows);
  renderDirectionChart(rows);
  renderMonthlyChart(rows);
  const has1D=activeTab!=='all'
    ?(vers[activeTab]?.hasYear&&rows.length>0)
    :Object.keys(vers).some(v=>vers[v].hasYear&&loaded[activeSym][v]?.length);
  const yearSection=document.getElementById('yearSection');
  if (has1D) { yearSection.style.display=''; renderYearChart(); }
  else        { yearSection.style.display='none'; destroyChart('year'); }
  renderTradeTable(rows);
  renderComparisonTable();
  renderTransactionsTable();
  renderPriceChart();
}





function hideDashboardData() {
  document.getElementById('balanceBar').style.display = 'none';
  document.getElementById('lastUpdated').style.display = 'none';
  document.getElementById('tabs').style.display = 'none';
  document.getElementById('cards').style.display = 'none';
  const panels = document.querySelectorAll('.panel');
  panels.forEach(p => p.style.display = 'none');
}
function showDashboardData() {
  document.getElementById('balanceBar').style.display = '';
  document.getElementById('lastUpdated').style.display = '';
  document.getElementById('tabs').style.display = '';
  document.getElementById('cards').style.display = '';
  const panels = document.querySelectorAll('.panel');
  panels.forEach(p => p.style.display = '');
}

let _pendingSymbolSelect = null;
async function handleSymbolSelect(newSym, dbInstance) {
  // If loaded is not ready, queue the request and retry soon
  if (typeof loaded === 'undefined' || !loaded) {
    _pendingSymbolSelect = { newSym, dbInstance };
    setTimeout(() => {
      if (_pendingSymbolSelect && typeof loaded !== 'undefined' && loaded) {
        const { newSym, dbInstance } = _pendingSymbolSelect;
        _pendingSymbolSelect = null;
        handleSymbolSelect(newSym, dbInstance);
      }
    }, 50);
    return;
  }
  // If another pending request is queued, clear it (only latest matters)
  _pendingSymbolSelect = null;
  console.log('[Dropdown] handleSymbolSelect proceeding for', newSym, 'dataset:', activeDataset);
  if (!newSym) {
    hideDashboardData();
    updateModeButtonStates();
    const removeBtn = document.getElementById('removeSymbolBtn');
    if (removeBtn) { removeBtn.disabled = true; removeBtn.style.opacity = '0.4'; }
    return;
  }
  if (newSym === activeSym) return;
  activeSym = newSym;
  resetTransactionFilters();
  activeTab = 'all'; tradeTablePage = 1; txPage = 1;
  const removeBtn = document.getElementById('removeSymbolBtn');
  if (removeBtn) { removeBtn.disabled = false; removeBtn.style.opacity = '1'; }
  if (!loaded[activeSym]) loaded[activeSym] = {};
  const vers = INSTRUMENTS[activeSym]?.versions;
  if (!vers) {
    hideDashboardData();
    updateModeButtonStates();
    return;
  }
  // Use dbInstance if provided, else window._SQL_DB
  const db = dbInstance || window._SQL_DB;
  console.log('[DEBUG] DB instance in handleSymbolSelect:', db);
  if (!db) {
    console.error('No SQL DB instance available');
    return;
  }
    // Prefer trade-level rows for every dataset. Symbol formats vary across
    // sources (e.g. BTC/USD vs BTC_USD), so query common aliases.
    const symbolAliases = getSymbolAliases(activeSym);
    const normalizedSymbol = getNormalizedSymbolKey(activeSym);
    const modeFilter = activeDataset === 'backtest' ? 'backtest' : (activeDataset === 'paper' ? 'paper' : 'live');
    let rows = [];
    try {
      const stmt = db.prepare(
        "SELECT * FROM trades WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ? AND mode = ? ORDER BY entry_time"
      );
      stmt.bind([normalizedSymbol, modeFilter]);
      while (stmt.step()) {
        rows.push(stmt.getAsObject());
      }
      stmt.free();
    } catch (e) {
      console.error('Error querying trades table:', e);
    }
    console.log('[DEBUG] trade rows fetched for', activeSym, 'aliases:', symbolAliases, 'normalized:', normalizedSymbol, 'count:', rows.length, rows);

    // Backtest fallback: older DB snapshots may only have summary rows.
    let summaryRows = [];
    if (activeDataset === 'backtest' && rows.length === 0) {
      try {
        const stmt = db.prepare(
          "SELECT metrics, notes, timestamp FROM backtest_results WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ? ORDER BY timestamp"
        );
        stmt.bind([normalizedSymbol]);
        while (stmt.step()) {
          summaryRows.push(stmt.getAsObject());
        }
        stmt.free();
      } catch (e) {
        console.error('Error querying backtest_results table:', e);
      }
      console.log('[DEBUG] backtest summary rows fetched for', activeSym, 'count:', summaryRows.length);
    }
    // Group by version and store in loaded cache
    const byVersion = {};
    if (activeDataset === 'backtest' && rows.length === 0) {
      summaryRows.forEach(r => {
        let metrics = null;
        try {
          metrics = JSON.parse(r.metrics || '{}');
        } catch (e) {
          metrics = null;
        }
        if (!metrics) return;
        let version = (metrics.version || '').toLowerCase();
        if (!version || !vers[version]) {
          const m = String(r.notes || '').match(/\b(v[1-6])\b/i);
          version = m ? m[1].toLowerCase() : 'v1';
        }
        if (!byVersion[version]) byVersion[version] = [];
        const startTime = metrics.first_trade_date || r.timestamp || null;
        const endTime = metrics.last_trade_date || metrics.first_trade_date || r.timestamp || null;
        const beginEq = Number(metrics.beginning_equity || getDatasetInitialCapital());
        const finalEq = Number(metrics.final_equity || beginEq);
        const netPnl = Number(metrics.total_pnl || (finalEq - beginEq));
        byVersion[version].push(
          {
            version,
            entry_time: startTime,
            exit_time: startTime,
            direction: 'long',
            entry_price: 0,
            exit_price: 0,
            result: 'OPEN',
            dollar_pnl: 0,
            equity: beginEq,
            _summary: metrics,
            _notes: r.notes || '',
          },
          {
            version,
            entry_time: endTime,
            exit_time: endTime,
            direction: 'long',
            entry_price: 0,
            exit_price: 0,
            result: 'TP',
            dollar_pnl: netPnl,
            equity: finalEq,
            _summary: metrics,
            _notes: r.notes || '',
          }
        );
      });
    } else {
      rows.forEach(r => {
        const versionKey = String(r.version || 'v1').toLowerCase();
        if (!byVersion[versionKey]) byVersion[versionKey] = [];
        byVersion[versionKey].push({
          ...r,
          version: versionKey,
        });
      });
    }
    Object.keys(vers).forEach(v => {
      loaded[activeSym][v] = byVersion[v] || [];
    });
    console.log('[DEBUG] byVersion keys:', Object.keys(byVersion), 'loaded[activeSym]:', loaded[activeSym]);
    // Show or hide dashboard based on whether any data was found
    const hasAnyData = Object.values(loaded[activeSym]).some(v => v && v.length > 0);
    console.log('[DEBUG] hasAnyData:', hasAnyData);
    const noDataNotice = document.getElementById('noDataNotice');
    if (noDataNotice) noDataNotice.style.display = hasAnyData ? 'none' : '';
    if (hasAnyData) {
      showDashboardData();
    } else {
      hideDashboardData();
      if (noDataNotice) noDataNotice.style.display = '';
    }
    buildTabs();
    render();
    updateLastUpdated();
    updateModeButtonStates();
}

// --- Ensure loadSymbolsAndInit is called at script end ---
hideDashboardData();
activeSym = '';
if (typeof loadSymbolsAndInit === 'function') {
  console.log('[DEBUG] Calling loadSymbolsAndInit at script end');
  loadSymbolsAndInit();
} else {
  console.error('[DEBUG] loadSymbolsAndInit is not defined');
}

async function handleBacktestVariantChange(ver, value) {
  if (!activeSym) return;
  backtestSelections[activeSym][ver] = value;
  if (activeMode !== 'backtest') return;
  loaded[activeSym][ver] = await loadCSV(activeSym, ver);
  buildTabs();
  render();
  updateLastUpdated();
}

document.getElementById('v1DatasetSelect')?.addEventListener('change', event => {
  handleBacktestVariantChange('v1', event.target.value);
});

document.getElementById('v2DatasetSelect')?.addEventListener('change', event => {
  handleBacktestVariantChange('v2', event.target.value);
});

(async () => {
  hideDashboardData();
  activeSym = '';

  let alpacaSymbolsCache = [];

  function normalizeSymbolType(value) {
    const raw = (value || '').toString().trim().toLowerCase();
    if (!raw) return 'stock';
    if (raw.includes('crypto')) return 'crypto';
    return 'stock';
  }

  function getSelectedSymbolTypes() {
    const checks = document.querySelectorAll('#alpacaTypeFilters input[type="checkbox"]');
    const selected = new Set();
    checks.forEach(chk => {
      if (chk.checked) selected.add(chk.value);
    });
    return selected;
  }

  function applyAlpacaSymbolTypeFilters() {
    const select = document.getElementById('alpacaSymbolSelect');
    const selectedTypes = getSelectedSymbolTypes();
    const filtered = alpacaSymbolsCache.filter(sym => selectedTypes.has(sym.type));

    select.innerHTML = '<option value="">Select a symbol...</option>';
    filtered.forEach(sym => {
      const opt = document.createElement('option');
      opt.value = sym.symbol;
      opt.textContent = sym.name ? `${sym.symbol} - ${sym.name}` : sym.symbol;
      select.appendChild(opt);
    });

    select.disabled = filtered.length === 0;
    if (filtered.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No symbols match selected type(s)';
      select.appendChild(opt);
      select.value = '';
    }
  }

  function renderAlpacaTypeFilters(symbolsData) {
    const wrap = document.getElementById('alpacaTypeFilters');
    if (!wrap) return;

    const types = [...new Set(symbolsData.map(item => normalizeSymbolType(item.type)))].sort();
    if (!types.length) {
      wrap.innerHTML = '';
      wrap.style.display = 'none';
      return;
    }

    wrap.innerHTML = '';
    types.forEach(type => {
      const label = document.createElement('label');
      label.style.display = 'inline-flex';
      label.style.alignItems = 'center';
      label.style.gap = '4px';
      label.style.cursor = 'pointer';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = type;
      checkbox.checked = true;
      checkbox.addEventListener('change', applyAlpacaSymbolTypeFilters);

      const text = document.createElement('span');
      text.textContent = type.charAt(0).toUpperCase() + type.slice(1);

      label.appendChild(checkbox);
      label.appendChild(text);
      wrap.appendChild(label);
    });

    wrap.style.display = 'inline-flex';
  }
  
  // Refresh symbols from local cache (alpaca_symbols table)
  async function loadAlpacaSymbols() {
    const select = document.getElementById('alpacaSymbolSelect');
    const loadBtn = document.getElementById('loadAlpacaSymbolsBtn');
    
    loadBtn.disabled = true;
    loadBtn.textContent = 'Refreshing...';
    select.innerHTML = '<option value="">Refreshing...</option>';
    
    try {
      // Use the local SQL.js DB instance if available, otherwise fetch DB file
      let db = window._SQL_DB;
      if (!db) {
        const dbPaths = ['data/tradingcopilot.db', 'docs/data/tradingcopilot.db'];
        let dbReq = null;
        for (const dbPath of dbPaths) {
          try {
            dbReq = await fetch(dbPath + '?v=' + Date.now());
            if (dbReq.ok) break;
          } catch (e) {}
        }
        if (!dbReq || !dbReq.ok) throw new Error('Could not load database file');
        
        const dbBuffer = await dbReq.arrayBuffer();
        const SQL = await window.initSqlJs({ locateFile: file => `https://cdn.jsdelivr.net/npm/sql.js@1.8.0/dist/${file}` });
        db = new SQL.Database(new Uint8Array(dbBuffer));
      }
      
      // Ensure alpaca_symbols table exists
      try {
        db.run(`
          CREATE TABLE IF NOT EXISTS alpaca_symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL,
            name TEXT,
            type TEXT,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
          )
        `);

        const tableInfoRes = db.exec('PRAGMA table_info(alpaca_symbols)');
        const colNames = tableInfoRes.length > 0 ? tableInfoRes[0].values.map(row => String(row[1])) : [];
        if (!colNames.includes('type')) {
          db.run("ALTER TABLE alpaca_symbols ADD COLUMN type TEXT DEFAULT 'stock'");
        }
      } catch (e) {
        console.warn('Could not ensure alpaca_symbols table exists:', e);
      }
      
      // Query alpaca_symbols table
      const res = db.exec('SELECT symbol, name, COALESCE(type, "stock") AS type FROM alpaca_symbols ORDER BY symbol');
      const symbols_data = [];
      
      if (res.length > 0) {
        const cols = res[0].columns;
        const values = res[0].values;
        symbols_data.push(...values.map(row => {
          const obj = {};
          cols.forEach((col, i) => { obj[col] = row[i]; });
          return obj;
        }));
      }
      
      if (symbols_data.length === 0) {
        const msg = 'Symbols cache is empty. Run the "Sync Alpaca Symbols to Database" workflow to populate this list. Go to GitHub Actions and trigger it manually.';
        select.innerHTML = '<option value="">Cache empty - see console message</option>';
        select.disabled = true;
        const filterWrap = document.getElementById('alpacaTypeFilters');
        if (filterWrap) {
          filterWrap.innerHTML = '';
          filterWrap.style.display = 'none';
        }
        loadBtn.disabled = false;
        loadBtn.textContent = 'Refresh';
        console.info(msg);
        alert(msg);
        return;
      }

      alpacaSymbolsCache = symbols_data.map(item => ({
        symbol: item.symbol,
        name: item.name,
        type: normalizeSymbolType(item.type),
      }));

      renderAlpacaTypeFilters(alpacaSymbolsCache);
      applyAlpacaSymbolTypeFilters();

      loadBtn.disabled = false;
      loadBtn.textContent = 'Refresh';
    } catch (err) {
      console.error('Error loading cached Alpaca symbols:', err);
      select.innerHTML = '<option value="">Error (see console)</option>';
      select.disabled = true;
      loadBtn.disabled = false;
      loadBtn.textContent = 'Refresh';
      alert('Error loading symbols: ' + err.message + '. Check browser console for details.');
    }
  }
  
  // Load Alpaca button
  const loadBtn = document.getElementById('loadAlpacaSymbolsBtn');
  loadBtn.addEventListener('click', loadAlpacaSymbols);
  
  // Add Symbol button logic (GitHub Issue automation)
  const select = document.getElementById('alpacaSymbolSelect');
  const addBtn = document.getElementById('addSymbolBtn');
  addBtn.addEventListener('click', () => {
    const symbol = select.value.trim();
    if (!symbol) {
      alert('Please select a symbol from the dropdown first.');
      return;
    }
    const desc = prompt('Enter a description for this symbol (optional):', '');
    // Open a pre-filled GitHub Issue for symbol addition with add-symbol label
    const title = encodeURIComponent('Add symbol: ' + symbol);
    const body = encodeURIComponent(
      `Symbol: ${symbol}\nDescription: ${desc || ''}\n\n_Selected from Alpaca Paper Trading assets via dashboard._`
    );
    const url = `https://github.com/rcaldwell67/pinescripts/issues/new?title=${title}&body=${body}&labels=add-symbol`;
    window.open(url, '_blank');
  });

  // Remove Symbol button logic (GitHub Issue automation)
  const removeBtn = document.getElementById('removeSymbolBtn');
  removeBtn.addEventListener('click', () => {
    if (!activeSym) return;
    const confirmed = confirm(`Remove symbol "${activeSym}" from the database?\n\nThis will open a GitHub issue to trigger the removal workflow.`);
    if (!confirmed) return;
    const title = encodeURIComponent('Remove symbol: ' + activeSym);
    const body = encodeURIComponent(
      `Symbol: ${activeSym}\n\n_This removal was requested from the dashboard UI._`
    );
    const url = `https://github.com/rcaldwell67/pinescripts/issues/new?title=${title}&body=${body}&labels=remove-symbol`;
    window.open(url, '_blank');
  });
})();

// Bind controls that were previously wired via inline HTML onchange handlers.
function bindStaticControlHandlers() {
  const txRerender = () => { txPage = 1; renderTransactionsTable(); };
  document.getElementById('txVerFilter')?.addEventListener('change', txRerender);
  document.getElementById('txTfFilter')?.addEventListener('change', txRerender);
  document.getElementById('txActionFilter')?.addEventListener('change', txRerender);
  document.getElementById('txDirFilter')?.addEventListener('change', txRerender);
  document.getElementById('txTypeFilter')?.addEventListener('change', txRerender);
  document.getElementById('txPageSizeSelect')?.addEventListener('change', e => {
    txPageSize = parseInt(e.target.value, 10);
    txPage = 1;
    renderTransactionsTable();
  });
  document.getElementById('tradePageSizeSelect')?.addEventListener('change', e => {
    tradePageSize = parseInt(e.target.value, 10);
    tradeTablePage = 1;
    renderTradeTable(getActiveRows());
  });
}

bindStaticControlHandlers();


