
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
  // Only v6 version is available in v6-only dashboard
  const versionTemplates = [
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
let paperTradeSourceFilter = 'simulation';
let simulationDataScopeFilter = 'historical';
let txPage = 1;
let txPageSize = 25;
let logsPage = 1;
let logsPageSize = 25;
let logsRenderSeq = 0;
const logsDataCache = {
  diagnosticRows: null,
  diagnosticPath: null,
};
const VERSION_KEYS = ['v6'];
const PAPER_TRADING_SUPPORTED_VERSIONS = new Set(VERSION_KEYS);
const LIVE_TRADING_SUPPORTED_VERSIONS = new Set(VERSION_KEYS);
// Guideline thresholds and policy overrides.
// These should match backend/config/guideline_policy.py to ensure consistency.
// To update: modify backend/config/guideline_policy.py and re-generate this section,
// or run: python backend/config/guideline_policy.py
const GUIDELINE_THRESHOLDS = {
  minTrades: 10,
  minWinRate: 65.0,
  minNetReturn: 15.0,
  maxDrawdown: 4.5,
};

// Symbol/version-specific guideline overrides.
// Key format: <NORMALIZED_SYMBOL>|<version>
const GUIDELINE_POLICY_OVERRIDES = {
  'BTCUSDC|v1': {
    advisoryOnly: ['winRate'],
  },
  'ETHUSDT|v3': {
    advisoryOnly: ['winRate'],
  },
  'ETHUSDC|v3': {
    advisoryOnly: ['trades'],
  },
  'CLM|v1': {
    advisoryOnly: ['trades'],
  },
  'CLM|v2': {
    advisoryOnly: ['trades'],
  },
  'CLM|v3': {
    advisoryOnly: ['trades'],
  },
  'CLM|v4': {
    advisoryOnly: ['trades'],
  },
  'CLM|v5': {
    advisoryOnly: ['trades'],
  },
  'CLM|v6': {
    advisoryOnly: ['trades'],
  },
  'CRF|v1': {
    advisoryOnly: ['trades'],
  },
  'CRF|v2': {
    advisoryOnly: ['trades'],
  },
  'CRF|v3': {
    advisoryOnly: ['trades'],
  },
  'CRF|v4': {
    advisoryOnly: ['trades'],
  },
  'CRF|v5': {
    advisoryOnly: ['trades'],
  },
  'CRF|v6': {
    advisoryOnly: ['trades'],
  },
};
let pendingDatasetSymbol = '';
let dashboardRefreshInFlight = false;
let dashboardAutoRefreshTimer = null;
let dailyValidationClipboardText = '';
let dailyTransactionsDateOffsetDays = 0;

function normalizeSource(value) {
  return String(value || '').toLowerCase() === 'realtime' ? 'realtime' : 'simulation';
}

function getUtcDateFromTimestamp(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const m = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : '';
}

function isSameDaySimulationTradeRow(row) {
  const dateKey = getUtcDateKey(0);
  const entryDate = getUtcDateFromTimestamp(row && row.entry_time);
  const exitDate = getUtcDateFromTimestamp(row && row.exit_time);
  return entryDate === dateKey || exitDate === dateKey;
}

function filterPaperRows(rows) {
  if (activeDataset !== 'paper') return rows;
  if (paperTradeSourceFilter === 'realtime') return rows.filter(r => normalizeSource(r.source) === 'realtime');
  if (paperTradeSourceFilter === 'simulation') {
    const simRows = rows.filter(r => normalizeSource(r.source) !== 'realtime');
    if (simulationDataScopeFilter === 'same_day') {
      return simRows.filter(isSameDaySimulationTradeRow);
    }
    return simRows;
  }
  return rows; // 'all'
}

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

function sqliteTableExists(db, tableName) {
  if (!db || !tableName) return false;
  const safeName = String(tableName).replace(/'/g, "''");
  try {
    const res = db.exec(`SELECT name FROM sqlite_master WHERE type='table' AND name='${safeName}'`);
    return Boolean(res.length && res[0].values && res[0].values.length);
  } catch (err) {
    return false;
  }
}

function getPaperFillStats(sym, monthStartMs = 0) {
  const db = window._SQL_DB;
  if (!db || !sym) return { mtdCount: 0, lastTs: 0 };

  const targetKey = getNormalizedSymbolKey(sym);
  if (!targetKey) return { mtdCount: 0, lastTs: 0 };

  let mtdCount = 0;
  let lastTs = 0;
  try {
    const stmt = db.prepare(`
      SELECT symbol, transaction_time
      FROM paper_fill_events
      ORDER BY datetime(transaction_time) DESC
    `);
    while (stmt.step()) {
      const row = stmt.getAsObject();
      if (getNormalizedSymbolKey(row.symbol) !== targetKey) continue;
      const ts = parseDashboardTimeValue(row.transaction_time);
      if (ts > lastTs) lastTs = ts;
      if (!monthStartMs || ts >= monthStartMs) mtdCount += 1;
    }
    stmt.free();
  } catch (err) {
    // Table may not exist in older DB snapshots.
  }

  return { mtdCount, lastTs };
}



  // --- Dataset selector logic ---
  let activeDataset = 'backtest'; // 'backtest', 'paper-sim', 'paper-rt', 'live'
  function getResultsJsonFile() {
    switch (activeDataset) {
      case 'backtest':
        return 'data/backtest_results.json';
      case 'paper-sim':
        return 'data/paper_trading_results.json';
      case 'paper-rt':
        return 'data/paper_trading_results.json'; // Could be a different file if needed
      case 'live':
        return 'data/live_trading_results.json';
      default:
        return 'data/backtest_results.json';
    }
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
        // Set filters for each mode
        if (activeDataset === 'paper-sim') {
          paperTradeSourceFilter = 'simulation';
        } else if (activeDataset === 'paper-rt') {
          paperTradeSourceFilter = 'realtime';
        } else {
          paperTradeSourceFilter = null;
        }
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
    // Try to load tradingcopilot.db, fallback to symbols.json if any error
    let symbols = [];
    let db = null;
    let usedFallback = false;
    try {
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
      if (!dbReq || !dbReq.ok) throw new Error('Failed to fetch tradingcopilot.db');
      const dbBuffer = await dbReq.arrayBuffer();
      console.log('[DEBUG] DB file loaded from', dbPathUsed, ', initializing sql.js...');
      // Initialize sql.js
      const SQL = await window.initSqlJs({ locateFile: file => `https://cdn.jsdelivr.net/npm/sql.js@1.8.0/dist/${file}` });
      db = new SQL.Database(new Uint8Array(dbBuffer));
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
      symbols = symbolsData.map(obj => obj.symbol);
      symbols = symbols.slice().sort((a, b) => a.localeCompare(b));
    } catch (err) {
      // Fallback to symbols.json
      usedFallback = true;
      console.warn('[FALLBACK] Using symbols.json due to DB error:', err);
      try {
        const resp = await fetch('data/symbols.json?v=' + Date.now());
        if (!resp.ok) throw new Error('Failed to fetch symbols.json');
        const json = await resp.json();
        symbols = (json || []).map(obj => obj.symbol).sort((a, b) => a.localeCompare(b));
      } catch (jsonErr) {
        console.error('[FALLBACK] Failed to load symbols.json:', jsonErr);
        symbols = [];
      }
    }
    window.SYMBOLS = symbols;
    buildSymbolSwitcher(symbols);

    // --- Restore symbol dropdown population logic ---
    const symbolSelect = document.getElementById('symbolSelect');
    if (symbolSelect) {
      // Remove all existing options
      while (symbolSelect.options.length > 0) {
        symbolSelect.remove(0);
      }
      // Add a default option
      const defaultOption = document.createElement('option');
      defaultOption.value = '';
      defaultOption.textContent = '-- Select Symbol --';
      symbolSelect.appendChild(defaultOption);
      // Add options for each symbol
      symbols.forEach(sym => {
        const opt = document.createElement('option');
        opt.value = sym;
        opt.textContent = sym;
        symbolSelect.appendChild(opt);
      });
      symbolSelect.disabled = false;
      // Restore selection if pendingDatasetSymbol or activeSym is set
      let toSelect = pendingDatasetSymbol || activeSym || '';
      if (toSelect && symbols.includes(toSelect)) {
        symbolSelect.value = toSelect;
      } else {
        symbolSelect.value = '';
      }
      // Attach event handler if not already bound
      if (!symbolSelect.dataset.bound) {
        symbolSelect.addEventListener('change', handleSymbolSelect);
        symbolSelect.dataset.bound = '1';
      }
    }

    // Save db instance for later use (may be null if fallback)
    window._SQL_DB = db;
    renderDailyValidationBadge();
    renderTransactionTicker();
    // Reset active selection so re-selecting the same symbol after a dataset
    // switch doesn't hit the early-exit guard in handleSymbolSelect.
    activeSym = '';
    pendingDatasetSymbol = '';
    // --- PATCH: If no symbols available, show error and keep dashboard visible ---
    const noDataNotice = document.getElementById('noDataNotice');
    if (symbols.length === 0) {
      if (noDataNotice) {
        noDataNotice.style.display = '';
        noDataNotice.textContent = 'No symbols are available. Data could not be loaded. Please check your deployment or data files.';
      }
      showDashboardData();
      // Do not hide dashboard panels on data load failure
    } else {
      if (noDataNotice) {
        noDataNotice.style.display = 'none';
        noDataNotice.textContent = 'No Data Is Available For That Selection';
      }
    }
    if (usedFallback) {
      console.warn('[FALLBACK] Symbol dropdown populated from symbols.json. Some features may be limited.');
    }
    console.log('[DEBUG] loadSymbolsAndInit complete');
  }



  console.log('[DEBUG] After DOMContentLoaded event handler registration');

  const DEFAULT_INITIAL_CAPITAL = 1000;
  const PAPER_INITIAL_CAPITAL = 100000;

  function hasRealtimePaperRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return false;
    return rows.some(r => normalizeSource(r.source) === 'realtime');
  }

  function getDatasetInitialCapital() {
    return activeDataset === 'paper' ? PAPER_INITIAL_CAPITAL : DEFAULT_INITIAL_CAPITAL;
  }

  function normalizeBeginningEquity(beginEq, rows = []) {
    if (!Number.isFinite(beginEq) || beginEq <= 0) return getDatasetInitialCapital();
    // Keep simulation baselines (typically 1000) intact so guideline metrics
    // match the strategy reports. Only coerce tiny baselines for broker-sourced
    // paper rows when needed.
    if (activeDataset === 'paper' && beginEq < 10000 && hasRealtimePaperRows(rows)) {
      return PAPER_INITIAL_CAPITAL;
    }
    return beginEq;
  }

  function getInitialCapitalFromRows(rows) {
    if (!rows || !rows.length) return getDatasetInitialCapital();
    if (rows[0]._summary) {
      const s = rows[0]._summary || {};
      const beginEq = Number(s.beginning_equity);
      return normalizeBeginningEquity(beginEq, rows);
    }
    const first = rows[0] || {};
    const eq = Number(first.equity);
    const pnl = Number(first.dollar_pnl);
    if (Number.isFinite(eq) && Number.isFinite(pnl)) {
      const beginEq = eq - pnl;
      if (Number.isFinite(beginEq) && beginEq > 0) return normalizeBeginningEquity(beginEq, rows);
    }
    return getDatasetInitialCapital();
  }

  function getDatasetCurrentBalance() {
    if (activeDataset !== 'paper' && activeDataset !== 'live') return null;
    const dataByMode = getLatestAccountInfoByMode();
    if (!dataByMode) return null;
    const row = activeDataset === 'paper' ? dataByMode.paper : dataByMode.live;
    const balance = Number(row && row.current_balance);
    if (!Number.isFinite(balance)) return null;
    return {
      value: balance,
      updatedAt: row && row.updated_at ? String(row.updated_at) : null,
      source: 'account',
    };
  }

  function getLatestEquityTimestampFromRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return null;
    const first = rows[0] || {};
    if (first._summary && first._summary.timestamp) {
      return String(first._summary.timestamp);
    }
    let bestMs = 0;
    let bestRaw = null;
    for (const row of rows) {
      const candidates = [row && row.exit_time, row && row.entry_time];
      for (const candidate of candidates) {
        if (!candidate) continue;
        const ms = parseDashboardTimeValue(candidate);
        if (ms > bestMs) {
          bestMs = ms;
          bestRaw = candidate;
        }
      }
    }
    return bestRaw ? String(bestRaw) : null;
  }

  function getSnapshotAgeInfo(snapshotTime) {
    if (!snapshotTime) {
      return { label: 'unknown age', state: 'is-stale' };
    }
    const rel = formatTickerRelativeTime(snapshotTime);
    const state = rel && rel.state ? rel.state : '';
    const label = rel && rel.label ? rel.label : 'unknown age';
    return { label, state };
  }

  function getSymbolInitialCapital(sym) {
    const byVersion = loaded?.[sym] || {};
    for (const rows of Object.values(byVersion)) {
      if (rows && rows.length) return getInitialCapitalFromRows(rows);
    }
    return getDatasetInitialCapital();
  }

  function formatCurrencySafe(value, fallback = '-') {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatTickerPrice(value) {
    const price = Number(value);
    if (!Number.isFinite(price)) return '-';
    if (Math.abs(price) < 100) return '$' + price.toFixed(4);
    return '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function formatTickerQuantity(value) {
    const qty = Number(value);
    if (!Number.isFinite(qty)) return null;
    return qty.toLocaleString('en-US', { maximumFractionDigits: 6 });
  }

  function formatTickerTimestamp(value) {
    if (!value) return '-';
    const date = new Date(String(value).replace(' ', 'T'));
    if (!Number.isFinite(date.getTime())) return String(value);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  function formatTickerRelativeTime(value) {
    const date = new Date(String(value || '').replace(' ', 'T'));
    if (!Number.isFinite(date.getTime())) return { label: 'unknown', state: '' };
    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.max(0, Math.round(diffMs / 60000));
    if (diffMin < 60) {
      return { label: `${diffMin}m ago`, state: diffMin <= 15 ? 'is-fresh' : '' };
    }
    if (diffMin < 1440) {
      const hours = Math.round(diffMin / 60);
      return { label: `${hours}h ago`, state: hours >= 24 ? 'is-stale' : '' };
    }
    const days = Math.round(diffMin / 1440);
    return { label: `${days}d ago`, state: 'is-stale' };
  }

  function formatTickerResultBadge(result, type) {
    if (type !== 'Close' || !result) return '';
    const resultUpper = String(result).toUpperCase().trim();
    if (resultUpper === 'TP') return `<span class="ticker-badge ticker-badge-tp" title="Target Profit">✓TP</span>`;
    if (resultUpper === 'SL') return `<span class="ticker-badge ticker-badge-sl" title="Stop Loss">✕SL</span>`;
    if (resultUpper === 'TRAIL' || resultUpper === 'TRAILING') return `<span class="ticker-badge ticker-badge-trail" title="Trailing Stop">⇄ TRAIL</span>`;
    return `<span class="ticker-badge ticker-badge-other" title="${escapeHtml(resultUpper)}">◆ ${escapeHtml(resultUpper.slice(0, 3))}</span>`;
  }

  function getTickerSymbolLabel(symbol) {
    const normalized = getNormalizedSymbolKey(symbol);
    const exact = INSTRUMENTS?.[symbol]?.label;
    if (exact) return exact;
    for (const [knownSymbol, info] of Object.entries(INSTRUMENTS || {})) {
      if (getNormalizedSymbolKey(knownSymbol) === normalized) return info.label || knownSymbol;
    }
    return String(symbol || '').replace(/_/g, '/');
  }

  function buildLatestTransactionsBySymbol() {
    const db = window._SQL_DB;
    if (!db) return [];
    if (activeDataset === 'live') return [];
    const latestBySymbol = new Map();
    const modeFilter = activeDataset === 'backtest' ? 'backtest' : (activeDataset === 'paper' ? 'paper' : 'live');
    const requireBrokerRows = activeDataset === 'live' || (activeDataset === 'paper' && paperTradeSourceFilter === 'realtime');
    const linkTable = modeFilter === 'live' ? 'live_order_trade_links' : 'paper_order_trade_links';
    const hasLinkTable = !requireBrokerRows || sqliteTableExists(db, linkTable);

    if (requireBrokerRows && !hasLinkTable) {
      return [];
    }

    try {
      const sourceClause = activeDataset === 'paper' && paperTradeSourceFilter === 'realtime'
        ? "AND COALESCE(LOWER(source), '') = 'realtime'"
        : '';
      const brokerClause = requireBrokerRows
        ? `AND EXISTS (SELECT 1 FROM ${linkTable} l WHERE l.trade_id = trades.id)`
        : '';
      // If a symbol is selected, filter for that symbol only
      const selectedSymbol = (typeof window !== 'undefined' && window.document) ? document.getElementById('symbolSelect')?.value : '';
      const symbolClause = selectedSymbol && selectedSymbol !== '' ? `AND symbol = ?` : '';
      const query = `
        SELECT *
        FROM trades
        WHERE mode = ?
        AND LOWER(version) = 'v6'
        ${sourceClause}
        ${brokerClause}
        ${symbolClause}
        ORDER BY datetime(COALESCE(exit_time, entry_time)) DESC, datetime(entry_time) DESC, id DESC
      `;
      const stmt = db.prepare(query);
      if (symbolClause) {
        stmt.bind([modeFilter, selectedSymbol]);
      } else {
        stmt.bind([modeFilter]);
      }
      // If a symbol is selected, just return the single latest event for that symbol (if any)
      if (symbolClause) {
        if (stmt.step()) {
          const row = stmt.getAsObject();
          const symbolKey = getNormalizedSymbolKey(row.symbol || '');
          if (!symbolKey) return [];
          const qty = row.qty ?? row.quantity ?? row.shares ?? row.size ?? null;
          const entryTime = parseDashboardTimeValue(row.entry_time);
          const exitTime = parseDashboardTimeValue(row.exit_time);
          const isLong = String(row.direction || '').toLowerCase() !== 'short';
          const events = [];
          if (entryTime > 0) {
            events.push({
              symbol: row.symbol,
              version: String(row.version || 'v1').toLowerCase(),
              action: isLong ? 'BUY' : 'SELL',
              type: 'Open',
              direction: String(row.direction || '-'),
              price: row.entry_price,
              qty,
              notional: Number.isFinite(Number(qty)) && Number.isFinite(Number(row.entry_price)) ? Number(qty) * Number(row.entry_price) : null,
              pnl: null,
              result: null,
              equity: null,
              timestamp: row.entry_time,
              sortTime: entryTime,
            });
          }
          if (exitTime > 0) {
            events.push({
              symbol: row.symbol,
              version: String(row.version || 'v1').toLowerCase(),
              action: isLong ? 'SELL' : 'BUY',
              type: 'Close',
              direction: String(row.direction || '-'),
              price: row.exit_price,
              qty,
              notional: Number.isFinite(Number(qty)) && Number.isFinite(Number(row.exit_price)) ? Number(qty) * Number(row.exit_price) : null,
              pnl: row.dollar_pnl,
              result: row.result,
              equity: row.equity,
              timestamp: row.exit_time,
              sortTime: exitTime,
            });
          }
          if (!events.length) return [];
          // Only show the latest event (open or close)
          const latestEvent = events.sort((a, b) => b.sortTime - a.sortTime)[0];
          return latestEvent ? [latestEvent] : [];
        }
        return [];
      }
      // Otherwise, show the latest for all symbols as before
      while (stmt.step()) {
        const row = stmt.getAsObject();
        if (activeDataset === 'paper') {
          const src = normalizeSource(row.source);
          if (paperTradeSourceFilter === 'realtime' && src !== 'realtime') continue;
          if (paperTradeSourceFilter === 'simulation' && src === 'realtime') continue;
        }
        const symbolKey = getNormalizedSymbolKey(row.symbol || '');
        if (!symbolKey) continue;

        const qty = row.qty ?? row.quantity ?? row.shares ?? row.size ?? null;
        const events = [];
        const entryTime = parseDashboardTimeValue(row.entry_time);
        const exitTime = parseDashboardTimeValue(row.exit_time);
        const isLong = String(row.direction || '').toLowerCase() !== 'short';

        if (entryTime > 0) {
          events.push({
            symbol: row.symbol,
            version: String(row.version || 'v1').toLowerCase(),
            action: isLong ? 'BUY' : 'SELL',
            type: 'Open',
            direction: String(row.direction || '-'),
            price: row.entry_price,
            qty,
            notional: Number.isFinite(Number(qty)) && Number.isFinite(Number(row.entry_price)) ? Number(qty) * Number(row.entry_price) : null,
            pnl: null,
            result: null,
            equity: null,
            timestamp: row.entry_time,
            sortTime: entryTime,
          });
        }
        if (exitTime > 0) {
          events.push({
            symbol: row.symbol,
            version: String(row.version || 'v1').toLowerCase(),
            action: isLong ? 'SELL' : 'BUY',
            type: 'Close',
            direction: String(row.direction || '-'),
            price: row.exit_price,
            qty,
            notional: Number.isFinite(Number(qty)) && Number.isFinite(Number(row.exit_price)) ? Number(qty) * Number(row.exit_price) : null,
            pnl: row.dollar_pnl,
            result: row.result,
            equity: row.equity,
            timestamp: row.exit_time,
            sortTime: exitTime,
          });
        }

        if (!events.length) continue;
        const latestEvent = events.sort((a, b) => b.sortTime - a.sortTime)[0];
        const current = latestBySymbol.get(symbolKey);
        if (!current || latestEvent.sortTime > current.sortTime) {
          latestBySymbol.set(symbolKey, latestEvent);
        }
      }
      stmt.free();
    } catch (err) {
      console.error('Error building transaction ticker items:', err);
      return [];
    }

    return [...latestBySymbol.values()].sort((a, b) => b.sortTime - a.sortTime);
  }

  function renderTransactionTicker() {
    const shell = document.getElementById('transactionTicker');
    const track = document.getElementById('transactionTickerTrack');
    if (!shell || !track) return;

    // Hide ticker if no data view is selected (shouldn't happen, but for safety)
    if (!activeDataset) {
      shell.style.display = 'none';
      return;
    }

    const items = buildLatestTransactionsBySymbol();
    shell.classList.remove('is-animated');

    // Show/hide ticker based on whether there are items for the current view
    if (!items.length) {
      shell.style.display = '';
      track.innerHTML = `<div class="ticker-empty">No recent ${escapeHtml(activeDataset)} transactions found.</div>`;
      return;
    }
    shell.style.display = '';

    const html = items.map(item => {
      const qtyText = formatTickerQuantity(item.qty);
      const amountText = Number.isFinite(Number(item.notional)) ? formatCurrencySafe(item.notional) : null;
      const pnlValue = Number(item.pnl);
      const pnlClass = Number.isFinite(pnlValue) ? (pnlValue >= 0 ? 'positive' : 'negative') : '';
      const resultText = item.result ? String(item.result).toUpperCase() : null;
      const equityText = Number.isFinite(Number(item.equity)) ? formatCurrencySafe(item.equity) : null;
      const direction = String(item.direction || '-').toLowerCase();
      const age = formatTickerRelativeTime(item.timestamp);
      const normalizedSymbol = getNormalizedSymbolKey(item.symbol);
      const resultBadge = formatTickerResultBadge(item.result, item.type);
      const main = [
        `<span class="ticker-symbol">${escapeHtml(getTickerSymbolLabel(item.symbol))}</span>`,
        `<span class="pill" style="background:${item.type === 'Open' ? '#58a6ff11' : '#21262d'};color:${item.type === 'Open' ? 'var(--muted)' : 'var(--text)'};border-color:${item.type === 'Open' ? '#58a6ff33' : 'var(--border)'}">${escapeHtml(item.type)}</span>`,
        `<span class="tag ${item.action === 'BUY' ? 'tag-buy' : 'tag-sell'}">${escapeHtml(item.action)}</span>`,
        `<span class="tag ${direction === 'short' ? 'tag-short' : 'tag-long'}">${escapeHtml(direction)}</span>`,
        resultBadge,
        `<span class="ticker-age ${escapeHtml(age.state)}">${escapeHtml(age.label)}</span>`,
      ].filter(Boolean);
      const meta = [
        `<span class="ticker-segment">ver <strong>${escapeHtml(item.version.toUpperCase())}</strong></span>`,
        `<span class="ticker-segment">px <strong>${escapeHtml(formatTickerPrice(item.price))}</strong></span>`,
      ];
      if (qtyText) meta.push(`<span class="ticker-segment">qty <strong>${escapeHtml(qtyText)}</strong></span>`);
      if (amountText) meta.push(`<span class="ticker-segment">amt <strong>${escapeHtml(amountText)}</strong></span>`);
      if (Number.isFinite(pnlValue)) meta.push(`<span class="ticker-segment ${pnlClass}">pnl <strong>${escapeHtml(formatCurrencySafe(pnlValue))}</strong></span>`);
      if (resultText) meta.push(`<span class="ticker-segment">res <strong>${escapeHtml(resultText)}</strong></span>`);
      if (equityText) meta.push(`<span class="ticker-segment">eq <strong>${escapeHtml(equityText)}</strong></span>`);
      meta.push(`<span class="ticker-segment">at <strong>${escapeHtml(formatTickerTimestamp(item.timestamp))}</strong></span>`);
      const isActive = normalizedSymbol && normalizedSymbol === getNormalizedSymbolKey(activeSym);
      return `<button type="button" class="ticker-item${isActive ? ' is-active' : ''}" data-symbol="${escapeHtml(item.symbol)}" title="Open ${escapeHtml(getTickerSymbolLabel(item.symbol))} in the dashboard"><span class="ticker-main">${main.join('')}</span><span class="ticker-meta">${meta.join('')}</span></button>`;
    }).join('');

    track.innerHTML = `<div class="ticker-group">${html}</div><div class="ticker-group" aria-hidden="true">${html}</div>`;
    track.style.setProperty('--ticker-duration', `${Math.max(24, items.length * 9)}s`);
    if (items.length > 1) {
      shell.classList.add('is-animated');
    } else {
      shell.classList.remove('is-animated');
    }
    const activeButton = track.querySelector('.ticker-item.is-active');
    if (activeButton) {
      setTimeout(() => activeButton.scrollIntoView({ behavior: 'auto', block: 'nearest', inline: 'center' }), 50);
    }

    // Re-trigger ticker animation on resize
    if (!shell._tickerResizeHandler) {
      shell._tickerResizeHandler = () => {
        if (items.length > 1) {
          shell.classList.remove('is-animated');
          // Force reflow to restart animation
          void shell.offsetWidth;
          shell.classList.add('is-animated');
        }
      };
      window.addEventListener('resize', shell._tickerResizeHandler);
    }
  }

  function _normalizeAccountMode(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'paper' || normalized === 'live') return normalized;
    return '';
  }

  function _inferAccountModeFromRow(row) {
    const event = String(row?.last_event || '').trim().toLowerCase();
    if (event.startsWith('live:') || event.includes(' live')) return 'live';
    if (event.startsWith('paper:') || event.includes('paper')) return 'paper';
    return '';
  }

  function getLatestAccountInfoByMode() {
    const db = window._SQL_DB;
    if (!db) return null;
    try {
      const schema = db.exec("PRAGMA table_info(Account_Info)");
      const hasAccountMode = Boolean(
        schema.length && schema[0].values.some(row => String(row[1] || '').toLowerCase() === 'account_mode')
      );
      const accountModeSelect = hasAccountMode ? 'account_mode' : "'' AS account_mode";
      const res = db.exec(`
        SELECT
          account_id,
          account_number,
          ${accountModeSelect},
          currency,
          status,
          beginning_balance,
          current_balance,
          buying_power,
          cash,
          last_event,
          updated_at
        FROM Account_Info
        ORDER BY datetime(updated_at) DESC
        LIMIT 50
      `);
      if (!res.length || !res[0].values.length) {
        return { paper: null, live: null };
      }
      const cols = res[0].columns;
      const rows = res[0].values.map(values => {
        const obj = {};
        cols.forEach((col, i) => {
          obj[col] = values[i];
        });
        return obj;
      });

      let paper = null;
      let live = null;
      const unknownRows = [];

      rows.forEach(row => {
        const explicitMode = _normalizeAccountMode(row.account_mode);
        const inferredMode = explicitMode || _inferAccountModeFromRow(row);
        if (inferredMode === 'paper' && !paper) {
          paper = row;
          return;
        }
        if (inferredMode === 'live' && !live) {
          live = row;
          return;
        }
        unknownRows.push(row);
      });

      if (!paper && unknownRows.length) paper = unknownRows.shift();
      if (!live && unknownRows.length) live = unknownRows.shift();

      return { paper, live };
    } catch (err) {
      console.error('Error querying Account_Info:', err);
      return null;
    }
  }

  function renderAccountInfoPanel(panelId, modeLabel, data) {
    const panel = document.getElementById(panelId);
    if (!panel) return;

    if (!data) {
      panel.innerHTML = [
        `<h3>${escapeHtml(modeLabel)} Account</h3>`,
        `<div class="account-panel-empty">No ${escapeHtml(modeLabel.toLowerCase())} account data found.</div>`,
      ].join('');
      return;
    }

    const normalizedMode = String(modeLabel || '').trim().toLowerCase() === 'live' ? 'live' : 'paper';
    const currentBalanceText = formatCurrencySafe(data.current_balance);
    const snapshotTime = data.updated_at ? String(data.updated_at) : null;
    const updatedLabel = snapshotTime ? formatTickerTimestamp(snapshotTime) : 'unknown';
    const age = getSnapshotAgeInfo(snapshotTime);
    const snapshotText = `${currentBalanceText} (${normalizedMode} account, ${updatedLabel})`;
    const snapshotHtml = `${escapeHtml(snapshotText)} <span class="snapshot-age ${escapeHtml(age.state)}">${escapeHtml(age.label)}</span>`;

    const rows = [
      { label: 'Account ID', value: String(data.account_id || '-') },
      { label: 'Account Number', value: String(data.account_number || '-') },
      { label: 'Status', value: String(data.status || '-') },
      { label: 'Currency', value: String(data.currency || '-') },
      { label: 'Current Equity Snapshot', value: snapshotHtml, isHtml: true },
      { label: 'Beginning Balance', value: formatCurrencySafe(data.beginning_balance) },
      { label: 'Current Balance', value: formatCurrencySafe(data.current_balance) },
      { label: 'Buying Power', value: formatCurrencySafe(data.buying_power) },
      { label: 'Cash', value: formatCurrencySafe(data.cash) },
      { label: 'Last Event', value: String(data.last_event || '-') },
      { label: 'Updated At', value: String(data.updated_at || '-') },
    ];
    const content = rows.map(row => {
      const renderedValue = row.isHtml
        ? String(row.value || '-')
        : escapeHtml(String(row.value ?? '-'));
      return `<div class="account-row"><span>${escapeHtml(row.label)}</span><strong>${renderedValue}</strong></div>`;
    }).join('');

    panel.innerHTML = `<h3>${escapeHtml(modeLabel)} Account</h3>${content}`;
  }

  function renderAccountInfoModal(dataByMode) {
    const paperData = dataByMode && dataByMode.paper ? dataByMode.paper : null;
    const liveData = dataByMode && dataByMode.live ? dataByMode.live : null;
    renderAccountInfoPanel('aiPaperPanel', 'Paper', paperData);
    renderAccountInfoPanel('aiLivePanel', 'Live', liveData);
  }

  function openAccountInfoModal() {
    const modal = document.getElementById('accountInfoModal');
    if (!modal) return;
    const data = getLatestAccountInfoByMode();
    renderAccountInfoModal(data);
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeAccountInfoModal() {
    const modal = document.getElementById('accountInfoModal');
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
  }

  function getUtcDateKey(offsetDays = 0) {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + Number(offsetDays || 0));
    return d.toISOString().slice(0, 10);
  }

  function getSelectedDailyTransactionsDateKey() {
    return getUtcDateKey(dailyTransactionsDateOffsetDays);
  }

  function updateDailyTransactionsDateControls() {
    const todayBtn = document.getElementById('dailyTransactionsTodayBtn');
    const yesterdayBtn = document.getElementById('dailyTransactionsYesterdayBtn');
    const label = document.getElementById('dailyTransactionsDateLabel');
    const dateKey = getSelectedDailyTransactionsDateKey();
    if (label) label.textContent = `UTC ${dateKey}`;
    if (todayBtn) {
      const isActive = dailyTransactionsDateOffsetDays === 0;
      todayBtn.classList.toggle('active', isActive);
      todayBtn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    }
    if (yesterdayBtn) {
      const isActive = dailyTransactionsDateOffsetDays === -1;
      yesterdayBtn.classList.toggle('active', isActive);
      yesterdayBtn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    }
  }

  function getTodayValidationSummary(dateKeyArg = null) {
    const db = window._SQL_DB;
    const dateKey = String(dateKeyArg || getUtcDateKey(0));
    const seedByVersion = Object.fromEntries(
      VERSION_KEYS.map(version => [version, { scheduleMiss: 0, missedOpportunity: 0, missedBlocked: 0 }])
    );
    if (!db) {
      return {
        dateKey,
        scheduleMiss: 0,
        missedOpportunity: 0,
        missedBlocked: 0,
        unscopedScheduleMiss: 0,
        byVersion: seedByVersion,
        latestScheduleMiss: null,
      };
    }

    const out = {
      dateKey,
      scheduleMiss: 0,
      missedOpportunity: 0,
      missedBlocked: 0,
      unscopedScheduleMiss: 0,
      byVersion: { ...seedByVersion },
      latestScheduleMiss: null,
    };

    try {
      const stmt = db.prepare(`
        SELECT version, status, logged_at, detail
        FROM realtime_paper_log
        WHERE substr(logged_at, 1, 10) = ?
        ORDER BY datetime(logged_at) DESC
      `);
      stmt.bind([dateKey]);
      while (stmt.step()) {
        const row = stmt.getAsObject();
        const version = String(row.version || 'unknown').toLowerCase();
        const status = String(row.status || '').toLowerCase();
        if (!out.byVersion[version]) {
          out.byVersion[version] = {
            scheduleMiss: 0,
            missedOpportunity: 0,
            missedBlocked: 0,
          };
        }

        if (status === 'schedule_miss') {
          out.scheduleMiss += 1;
          if (version === 'system' || version === 'unknown' || !out.byVersion[version]) {
            out.unscopedScheduleMiss += 1;
          } else {
            out.byVersion[version].scheduleMiss += 1;
          }
          if (!out.latestScheduleMiss) {
            out.latestScheduleMiss = {
              loggedAt: String(row.logged_at || ''),
              detail: String(row.detail || ''),
            };
          }
        } else if (status === 'missed_opportunity') {
          out.missedOpportunity += 1;
          out.byVersion[version].missedOpportunity += 1;
        } else if (status === 'missed_opportunity_blocked') {
          out.missedBlocked += 1;
          out.byVersion[version].missedBlocked += 1;
        }
      }
      stmt.free();
    } catch (err) {
      console.error('Error querying realtime_paper_log validation summary:', err);
    }

    const accountedScheduleMiss = VERSION_KEYS.reduce(
      (sum, version) => sum + Number(out.byVersion[version]?.scheduleMiss || 0),
      0,
    );
    if (out.scheduleMiss > accountedScheduleMiss) {
      out.unscopedScheduleMiss = Math.max(
        Number(out.unscopedScheduleMiss || 0),
        out.scheduleMiss - accountedScheduleMiss,
      );
    }

    return out;
  }

  let dailyValidationPopoverHideTimer = null;

  function clearDailyValidationPopoverHideTimer() {
    if (dailyValidationPopoverHideTimer) {
      clearTimeout(dailyValidationPopoverHideTimer);
      dailyValidationPopoverHideTimer = null;
    }
  }

  function queueHideDailyValidationPopover(delayMs = 160) {
    clearDailyValidationPopoverHideTimer();
    dailyValidationPopoverHideTimer = setTimeout(() => {
      hideDailyValidationPopover();
    }, Math.max(0, delayMs));
  }

  function hideDailyValidationPopover() {
    clearDailyValidationPopoverHideTimer();
    const pop = document.getElementById('dailyValidationPopover');
    if (!pop) return;
    pop.classList.remove('open');
    pop.setAttribute('aria-hidden', 'true');
  }

  function showDailyValidationPopover() {
    clearDailyValidationPopoverHideTimer();
    const badge = document.getElementById('dailyValidationBadge');
    const pop = document.getElementById('dailyValidationPopover');
    if (!badge || !pop || pop.innerHTML.trim() === '') return;

    const rect = badge.getBoundingClientRect();
    const gap = 8;
    const maxLeft = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
    const left = Math.max(8, Math.min(rect.left, maxLeft));
    const top = rect.bottom + gap;

    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
    pop.classList.add('open');
    pop.setAttribute('aria-hidden', 'false');
  }

  async function copyDailyValidationSummary() {
    const text = String(dailyValidationClipboardText || '').trim();
    if (!text) return false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', 'true');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      return true;
    } catch (err) {
      console.warn('Copy daily validation summary failed:', err);
      return false;
    }
  }

  function setDailyValidationCopyStatus(message, isError = false) {
    const el = document.getElementById('dailyValidationCopyStatus');
    if (!el) return;
    el.textContent = message;
    el.style.color = isError ? '#f85149' : '#8b949e';
    if (message) {
      setTimeout(() => {
        const current = document.getElementById('dailyValidationCopyStatus');
        if (current && current.textContent === message) current.textContent = '';
      }, 1800);
    }
  }

  function renderDailyValidationBadge() {
    const badge = document.getElementById('dailyValidationBadge');
    const pop = document.getElementById('dailyValidationPopover');
    if (!badge) return;

    const summary = getTodayValidationSummary();
    const scheduleMiss = Number(summary.scheduleMiss || 0);
    const unscopedScheduleMiss = Number(summary.unscopedScheduleMiss || 0);
    const missed = Number(summary.missedOpportunity || 0);
    const blocked = Number(summary.missedBlocked || 0);
    const versionLines = Object.keys(summary.byVersion || {})
      .sort()
      .filter(version => version && version !== 'system')
      .map(version => {
        const row = summary.byVersion[version] || {};
        return `${version}: gaps=${Number(row.scheduleMiss || 0)}, missed=${Number(row.missedOpportunity || 0)}, blocked=${Number(row.missedBlocked || 0)}`;
      });

    if (pop) {
      const versionHtml = versionLines.length
        ? versionLines.map(line => `<div class="vp-version">${escapeHtml(line)}</div>`).join('')
        : '<div class="vp-detail">No version-specific rows for today.</div>';
      const latestDetail = summary.latestScheduleMiss && summary.latestScheduleMiss.detail
        ? escapeHtml(String(summary.latestScheduleMiss.detail))
        : '';
      const latestAt = summary.latestScheduleMiss && summary.latestScheduleMiss.loggedAt
        ? escapeHtml(String(summary.latestScheduleMiss.loggedAt))
        : '';

      const clipLines = [
        `UTC ${summary.dateKey || ''}`,
        `schedule_miss=${scheduleMiss}`,
        `schedule_miss_unscoped=${unscopedScheduleMiss}`,
        `missed_opportunity=${missed}`,
        `missed_opportunity_blocked=${blocked}`,
      ];
      if (versionLines.length) {
        clipLines.push('', 'By version:', ...versionLines);
      }
      if (summary.latestScheduleMiss && summary.latestScheduleMiss.loggedAt) {
        clipLines.push('', `Latest Scheduler Gap: ${String(summary.latestScheduleMiss.loggedAt)}`);
        if (summary.latestScheduleMiss.detail) {
          clipLines.push(String(summary.latestScheduleMiss.detail));
        }
      }
      dailyValidationClipboardText = clipLines.join('\n');

      pop.innerHTML = `
        <div class="vp-title">UTC ${escapeHtml(summary.dateKey || '')}</div>
        <div class="vp-row"><span class="k">schedule_miss</span><strong>${scheduleMiss}</strong></div>
        <div class="vp-row"><span class="k">schedule_miss_unscoped</span><strong>${unscopedScheduleMiss}</strong></div>
        <div class="vp-row"><span class="k">missed_opportunity</span><strong>${missed}</strong></div>
        <div class="vp-row"><span class="k">missed_opportunity_blocked</span><strong>${blocked}</strong></div>
        <div class="vp-copy-row">
          <button id="copyDailyValidationBtn" type="button" class="vp-copy-btn">Copy Summary</button>
          <span id="dailyValidationCopyStatus" class="vp-copy-status" aria-live="polite"></span>
        </div>
        <div class="vp-sep"></div>
        <div class="vp-title">By Version</div>
        ${versionHtml}
        ${latestAt ? `<div class="vp-sep"></div><div class="vp-title">Latest Scheduler Gap</div><div class="vp-detail">${latestAt}</div>` : ''}
        ${latestDetail ? `<div class="vp-detail">${latestDetail}</div>` : ''}
      `;
    }

    badge.style.display = '';
    if (missed > 0) {
      badge.textContent = `Validation: FAIL (missed=${missed})`;
      badge.style.borderColor = '#f85149';
      badge.style.color = '#f85149';
      badge.style.background = 'rgba(248,81,73,0.08)';
      return;
    }

    if (scheduleMiss > 0 || blocked > 0) {
      badge.textContent = `Validation: WARN (gaps=${scheduleMiss}, blocked=${blocked})`;
      badge.style.borderColor = '#ffa657';
      badge.style.color = '#ffa657';
      badge.style.background = 'rgba(255,166,87,0.08)';
      return;
    }

    badge.textContent = 'Validation: PASS';
    badge.style.borderColor = '#3fb950';
    badge.style.color = '#3fb950';
    badge.style.background = 'rgba(63,185,80,0.08)';
  }

  function getTodayTransactions(dateKeyArg = null) {
    const db = window._SQL_DB;
    if (!db) return { fills: [], orders: [], simulationEvents: [] };

    const dateKey = String(dateKeyArg || getUtcDateKey(0));
    const todayStart = `${dateKey}T00:00:00.000Z`;
    const nextDay = new Date(`${dateKey}T00:00:00.000Z`);
    nextDay.setUTCDate(nextDay.getUTCDate() + 1);
    const tomorrowStr = nextDay.toISOString();

    const fills = [];
    const orders = [];
    const simulationEvents = [];

    try {
      // Query paper fills
      try {
        const fillStmt = db.prepare(`
          SELECT
            f.symbol,
            f.side,
            f.qty,
            f.price,
            f.transaction_time,
            f.order_id,
            COALESCE(LOWER(l.version), 'unknown') AS version
          FROM paper_fill_events f
          LEFT JOIN paper_order_trade_links l ON l.order_id = f.order_id
          WHERE f.transaction_time >= ? AND f.transaction_time < ?
          ORDER BY datetime(transaction_time) DESC
        `);
        fillStmt.bind([todayStart, tomorrowStr]);
        while (fillStmt.step()) {
          const row = fillStmt.getAsObject();
          fills.push({ ...row, mode: 'paper' });
        }
        fillStmt.free();
      } catch (err) {
        console.debug('Paper fills query error:', err);
      }

      // Query live fills if table exists
      try {
        const liveTableExists = db.exec("SELECT name FROM sqlite_master WHERE type='table' AND name='live_fill_events'").length > 0;
        if (liveTableExists) {
          const liveFillStmt = db.prepare(`
            SELECT
              f.symbol,
              f.side,
              f.qty,
              f.price,
              f.transaction_time,
              f.order_id,
              COALESCE(LOWER(l.version), 'unknown') AS version
            FROM live_fill_events f
            LEFT JOIN live_order_trade_links l ON l.order_id = f.order_id
            WHERE f.transaction_time >= ? AND f.transaction_time < ?
            ORDER BY datetime(transaction_time) DESC
          `);
          liveFillStmt.bind([todayStart, tomorrowStr]);
          while (liveFillStmt.step()) {
            const row = liveFillStmt.getAsObject();
            fills.push({ ...row, mode: 'live' });
          }
          liveFillStmt.free();
        }
      } catch (err) {
        console.debug('Live fills query error:', err);
      }

      // Query paper orders
      try {
        const orderStmt = db.prepare(`
          SELECT
            o.symbol,
            o.status,
            o.event_type,
            o.event_time,
            o.order_id,
            o.qty,
            o.notional,
            o.filled_qty,
            COALESCE(LOWER(l.version), 'unknown') AS version
          FROM paper_order_events o
          LEFT JOIN paper_order_trade_links l ON l.order_id = o.order_id
          WHERE o.event_time >= ? AND o.event_time < ?
          ORDER BY datetime(event_time) DESC
        `);
        orderStmt.bind([todayStart, tomorrowStr]);
        while (orderStmt.step()) {
          const row = orderStmt.getAsObject();
          orders.push({ ...row, mode: 'paper' });
        }
        orderStmt.free();
      } catch (err) {
        console.debug('Paper orders query error:', err);
      }

      // Query live orders if table exists
      try {
        const liveTableExists = db.exec("SELECT name FROM sqlite_master WHERE type='table' AND name='live_order_events'").length > 0;
        if (liveTableExists) {
          const liveOrderStmt = db.prepare(`
            SELECT
              o.symbol,
              o.status,
              o.event_type,
              o.event_time,
              o.order_id,
              o.qty,
              o.notional,
              o.filled_qty,
              COALESCE(LOWER(l.version), 'unknown') AS version
            FROM live_order_events o
            LEFT JOIN live_order_trade_links l ON l.order_id = o.order_id
            WHERE o.event_time >= ? AND o.event_time < ?
            ORDER BY datetime(event_time) DESC
          `);
          liveOrderStmt.bind([todayStart, tomorrowStr]);
          while (liveOrderStmt.step()) {
            const row = liveOrderStmt.getAsObject();
            orders.push({ ...row, mode: 'live' });
          }
          liveOrderStmt.free();
        }
      } catch (err) {
        console.debug('Live orders query error:', err);
      }

      // Query simulated paper trades (non-realtime) as open/close events.
      try {
        const simStmt = db.prepare(`
          SELECT
            symbol,
            LOWER(version) AS version,
            entry_time,
            exit_time,
            direction,
            entry_price,
            exit_price,
            result,
            dollar_pnl
          FROM trades
          WHERE mode = 'paper'
            AND LOWER(COALESCE(source, '')) != 'realtime'
            AND (
              (entry_time >= ? AND entry_time < ?)
              OR (exit_time >= ? AND exit_time < ?)
            )
          ORDER BY datetime(COALESCE(exit_time, entry_time)) DESC, id DESC
        `);
        simStmt.bind([todayStart, tomorrowStr, todayStart, tomorrowStr]);
        while (simStmt.step()) {
          const row = simStmt.getAsObject();
          const symbol = String(row.symbol || '');
          const version = String(row.version || 'unknown');
          const direction = String(row.direction || '').toLowerCase();
          const entryTime = row.entry_time || null;
          const exitTime = row.exit_time || null;

          if (entryTime && entryTime >= todayStart && entryTime < tomorrowStr) {
            simulationEvents.push({
              event_time: entryTime,
              symbol,
              version,
              event_type: 'open',
              direction,
              price: row.entry_price,
              pnl: null,
              result: null,
              mode: 'simulation',
            });
          }
          if (exitTime && exitTime >= todayStart && exitTime < tomorrowStr) {
            simulationEvents.push({
              event_time: exitTime,
              symbol,
              version,
              event_type: 'close',
              direction,
              price: row.exit_price,
              pnl: row.dollar_pnl,
              result: row.result,
              mode: 'simulation',
            });
          }
        }
        simStmt.free();
      } catch (err) {
        console.debug('Simulation trade query error:', err);
      }

    } catch (err) {
      console.error('Error reading transactions:', err);
    }

    return { fills, orders, simulationEvents };
  }

  function renderDailyTransactionsModal() {
    const modal = document.getElementById('dailyTransactionsModal');
    const contentDiv = document.getElementById('dailyTransactionsContent');
    if (!modal || !contentDiv) return;
    updateDailyTransactionsDateControls();

    const dateKey = getSelectedDailyTransactionsDateKey();
    const { fills, orders, simulationEvents } = getTodayTransactions(dateKey);
    const validation = getTodayValidationSummary(dateKey);
    const totalTransactions = fills.length + orders.length + simulationEvents.length;
    const executableMisses = validation.missedOpportunity;
    const blockedMisses = validation.missedBlocked;
    const scheduleMisses = validation.scheduleMiss;
    const unscopedScheduleMisses = validation.unscopedScheduleMiss || 0;

    const summaryTone = executableMisses > 0
      ? '#f85149'
      : (scheduleMisses > 0 ? '#ffa657' : '#3fb950');
    const summaryLabel = executableMisses > 0
      ? 'Attention: executable missed opportunities found today'
      : (scheduleMisses > 0
        ? 'No executable missed opportunities, but scheduler gaps detected'
        : 'Validation looks healthy for today');

    let html = `<div style="padding: 10px 0;">
      <div style="border:1px solid var(--border); border-left:4px solid ${summaryTone}; border-radius:8px; padding:10px 12px; margin-bottom:14px; background:rgba(255,255,255,0.02);">
        <div style="font-size:12px; color:var(--muted); margin-bottom:6px;">UTC ${validation.dateKey}</div>
        <div style="font-size:13px; font-weight:600; color:${summaryTone}; margin-bottom:8px;">${summaryLabel}</div>
        <div style="display:flex; flex-wrap:wrap; gap:8px;">
          <span style="font-size:12px; padding:4px 8px; border-radius:999px; background:#2f81f71a; color:#58a6ff; border:1px solid #2f81f733;">schedule_miss: ${scheduleMisses}</span>
          <span style="font-size:12px; padding:4px 8px; border-radius:999px; background:#f2cc601a; color:#f2cc60; border:1px solid #f2cc6033;">schedule_miss_unscoped: ${unscopedScheduleMisses}</span>
          <span style="font-size:12px; padding:4px 8px; border-radius:999px; background:${executableMisses > 0 ? '#f851491a' : '#3fb9501a'}; color:${executableMisses > 0 ? '#f85149' : '#3fb950'}; border:1px solid ${executableMisses > 0 ? '#f8514933' : '#3fb95033'};">missed_opportunity: ${executableMisses}</span>
          <span style="font-size:12px; padding:4px 8px; border-radius:999px; background:#ffa6571a; color:#ffa657; border:1px solid #ffa65733;">missed_opportunity_blocked: ${blockedMisses}</span>
        </div>
      </div>`;

    const versionRows = VERSION_KEYS
      .map(version => {
        const row = validation.byVersion[version] || { scheduleMiss: 0, missedOpportunity: 0, missedBlocked: 0 };
        return `<tr style="border-bottom:1px solid #eee;">
          <td style="padding:6px; font-weight:600;">${version}</td>
          <td style="padding:6px; text-align:right;">${row.scheduleMiss}</td>
          <td style="padding:6px; text-align:right;">${row.missedOpportunity}</td>
          <td style="padding:6px; text-align:right;">${row.missedBlocked}</td>
        </tr>`;
      })
      .join('');

    const unscopedRow = unscopedScheduleMisses > 0
      ? `<tr style="border-bottom:1px solid #eee;">
          <td style="padding:6px; font-weight:600;">system (unscoped)</td>
          <td style="padding:6px; text-align:right;">${unscopedScheduleMisses}</td>
          <td style="padding:6px; text-align:right;">0</td>
          <td style="padding:6px; text-align:right;">0</td>
        </tr>`
      : '';

    if (versionRows || unscopedRow) {
      html += `<div style="margin-bottom:16px;">
        <h3 style="margin:0 0 8px 0; font-size:14px; text-transform:uppercase; color:#666;">Validation By Version</h3>
        <table style="width:100%; border-collapse:collapse; font-size:12px;">
          <thead>
            <tr style="border-bottom:1px solid #ddd;">
              <th style="padding:6px; text-align:left; color:#666;">Version</th>
              <th style="padding:6px; text-align:right; color:#666;">Schedule Miss</th>
              <th style="padding:6px; text-align:right; color:#666;">Missed Opp</th>
              <th style="padding:6px; text-align:right; color:#666;">Blocked</th>
            </tr>
          </thead>
          <tbody>${versionRows}${unscopedRow}</tbody>
        </table>
      </div>`;
    }

    if (totalTransactions === 0) {
      html += '<p style="color: #999; text-align: center; padding: 20px;">No transactions today</p></div>';
      contentDiv.innerHTML = html;
      return;
    }

    if (orders.length > 0) {
      html += `<div style="margin-bottom: 20px;">
        <h3 style="margin: 0 0 10px 0; font-size: 14px; text-transform: uppercase; color: #666;">Orders (${orders.length})</h3>
        <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
          <thead>
            <tr style="border-bottom: 1px solid #ddd;">
              <th style="padding: 6px; text-align: left; color: #666;">Time</th>
              <th style="padding: 6px; text-align: left; color: #666;">Symbol</th>
              <th style="padding: 6px; text-align: left; color: #666;">Type</th>
              <th style="padding: 6px; text-align: left; color: #666;">Status</th>
              <th style="padding: 6px; text-align: left; color: #666;">Version</th>
              <th style="padding: 6px; text-align: right; color: #666;">Qty</th>
              <th style="padding: 6px; text-align: right; color: #666;">Notional</th>
              <th style="padding: 6px; text-align: left; color: #666;">Mode</th>
            </tr>
          </thead>
          <tbody>`;

      for (const order of orders) {
        const time = order.event_time ? new Date(order.event_time.replace(' ', 'T')).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-';
        const symbol = order.symbol || '-';
        const eventType = order.event_type || '-';
        const status = order.status || '-';
        const version = order.version ? String(order.version).toUpperCase() : 'UNKNOWN';
        const qty = order.qty ? Number(order.qty).toFixed(4) : '-';
        const notional = order.notional ? '$' + Number(order.notional).toFixed(2) : '-';
        const mode = order.mode ? `<span style="background: ${order.mode === 'live' ? '#ffcccc' : '#ccf'}; padding: 2px 6px; border-radius: 3px; font-size: 11px;">${order.mode}</span>` : '-';

        html += `<tr style="border-bottom: 1px solid #eee;">
          <td style="padding: 6px;">${time}</td>
          <td style="padding: 6px; font-weight: bold;">${symbol}</td>
          <td style="padding: 6px;">${eventType}</td>
          <td style="padding: 6px;"><span style="background: ${status === 'submitted' || status === 'filled' ? '#90EE90' : status === 'rejected' ? '#FFB6C6' : '#F0F0F0'}; padding: 2px 6px; border-radius: 3px; font-size: 11px;">${status}</span></td>
          <td style="padding: 6px; font-weight: 600;">${version}</td>
          <td style="padding: 6px; text-align: right;">${qty}</td>
          <td style="padding: 6px; text-align: right;">${notional}</td>
          <td style="padding: 6px;">${mode}</td>
        </tr>`;
      }
      html += `</tbody></table></div>`;
    }

    if (simulationEvents.length > 0) {
      html += `<div style="margin-bottom: 20px;">
        <h3 style="margin: 0 0 10px 0; font-size: 14px; text-transform: uppercase; color: #666;">Simulation Trades (${simulationEvents.length})</h3>
        <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
          <thead>
            <tr style="border-bottom: 1px solid #ddd;">
              <th style="padding: 6px; text-align: left; color: #666;">Time</th>
              <th style="padding: 6px; text-align: left; color: #666;">Symbol</th>
              <th style="padding: 6px; text-align: left; color: #666;">Event</th>
              <th style="padding: 6px; text-align: left; color: #666;">Direction</th>
              <th style="padding: 6px; text-align: left; color: #666;">Version</th>
              <th style="padding: 6px; text-align: right; color: #666;">Price</th>
              <th style="padding: 6px; text-align: right; color: #666;">P&L</th>
              <th style="padding: 6px; text-align: left; color: #666;">Result</th>
            </tr>
          </thead>
          <tbody>`;

      for (const ev of simulationEvents) {
        const time = ev.event_time ? new Date(String(ev.event_time).replace(' ', 'T')).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-';
        const symbol = ev.symbol || '-';
        const eventType = String(ev.event_type || '-').toUpperCase();
        const direction = String(ev.direction || '-').toUpperCase();
        const version = ev.version ? String(ev.version).toUpperCase() : 'UNKNOWN';
        const priceNum = Number(ev.price);
        const price = Number.isFinite(priceNum) ? '$' + priceNum.toFixed(2) : '-';
        const pnlNum = Number(ev.pnl);
        const pnl = Number.isFinite(pnlNum)
          ? (pnlNum >= 0 ? '+' : '-') + '$' + Math.abs(pnlNum).toFixed(2)
          : '-';
        const result = ev.result ? String(ev.result).toUpperCase() : '-';

        html += `<tr style="border-bottom: 1px solid #eee;">
          <td style="padding: 6px;">${time}</td>
          <td style="padding: 6px; font-weight: bold;">${symbol}</td>
          <td style="padding: 6px;"><span style="background:${eventType === 'OPEN' ? '#58a6ff22' : '#3fb95022'}; padding: 2px 6px; border-radius: 3px; font-size: 11px;">${eventType}</span></td>
          <td style="padding: 6px;">${direction}</td>
          <td style="padding: 6px; font-weight: 600;">${version}</td>
          <td style="padding: 6px; text-align: right;">${price}</td>
          <td style="padding: 6px; text-align: right; font-weight: 600; color: ${Number.isFinite(pnlNum) ? (pnlNum >= 0 ? '#3fb950' : '#f85149') : 'var(--muted)'};">${pnl}</td>
          <td style="padding: 6px;">${result}</td>
        </tr>`;
      }
      html += `</tbody></table></div>`;
    }

    if (fills.length > 0) {
      html += `<div style="margin-bottom: 20px;">
        <h3 style="margin: 0 0 10px 0; font-size: 14px; text-transform: uppercase; color: #666;">Fills (${fills.length})</h3>
        <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
          <thead>
            <tr style="border-bottom: 1px solid #ddd;">
              <th style="padding: 6px; text-align: left; color: #666;">Time</th>
              <th style="padding: 6px; text-align: left; color: #666;">Symbol</th>
              <th style="padding: 6px; text-align: left; color: #666;">Side</th>
              <th style="padding: 6px; text-align: left; color: #666;">Version</th>
              <th style="padding: 6px; text-align: right; color: #666;">Qty</th>
              <th style="padding: 6px; text-align: right; color: #666;">Price</th>
              <th style="padding: 6px; text-align: right; color: #666;">Total</th>
              <th style="padding: 6px; text-align: left; color: #666;">Mode</th>
            </tr>
          </thead>
          <tbody>`;

      for (const fill of fills) {
        const time = fill.transaction_time ? new Date(fill.transaction_time.replace(' ', 'T')).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-';
        const symbol = fill.symbol || '-';
        const side = fill.side || '-';
        const version = fill.version ? String(fill.version).toUpperCase() : 'UNKNOWN';
        const qty = fill.qty ? Number(fill.qty).toFixed(4) : '-';
        const price = fill.price ? '$' + Number(fill.price).toFixed(2) : '-';
        const total = (fill.qty && fill.price) ? '$' + (Number(fill.qty) * Number(fill.price)).toFixed(2) : '-';
        const mode = fill.mode ? `<span style="background: ${fill.mode === 'live' ? '#ffcccc' : '#ccf'}; padding: 2px 6px; border-radius: 3px; font-size: 11px;">${fill.mode}</span>` : '-';

        html += `<tr style="border-bottom: 1px solid #eee; background: ${side === 'buy' ? 'rgba(144, 238, 144, 0.1)' : 'rgba(255, 182, 193, 0.1)'};">
          <td style="padding: 6px;">${time}</td>
          <td style="padding: 6px; font-weight: bold;">${symbol}</td>
          <td style="padding: 6px; text-transform: uppercase; font-weight: bold; color: ${side === 'buy' ? '#008000' : '#CC0000'}">${side}</td>
          <td style="padding: 6px; font-weight: 600;">${version}</td>
          <td style="padding: 6px; text-align: right;">${qty}</td>
          <td style="padding: 6px; text-align: right;">${price}</td>
          <td style="padding: 6px; text-align: right; font-weight: bold;">${total}</td>
          <td style="padding: 6px;">${mode}</td>
        </tr>`;
      }
      html += `</tbody></table></div>`;
    }

    html += `</div>`;
    contentDiv.innerHTML = html;
    renderDailyValidationBadge();
  }

  function openDailyTransactionsModal() {
    const modal = document.getElementById('dailyTransactionsModal');
    if (!modal) return;
    updateDailyTransactionsDateControls();
    renderDailyTransactionsModal();
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeDailyTransactionsModal() {
    const modal = document.getElementById('dailyTransactionsModal');
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
  }

  // ── Trade Gap Analysis modal ────────────────────────────────────────────────

  function computeTradeGapAnalysis() {
    const db = window._SQL_DB;
    if (!db) return [];

    const rows = [];
    try {
      const stmt = db.prepare(
        "SELECT symbol, version, mode, entry_time FROM trades " +
        "WHERE mode IN ('backtest','paper') AND entry_time IS NOT NULL " +
        "ORDER BY symbol, version, mode, entry_time"
      );
      while (stmt.step()) rows.push(stmt.getAsObject());
      stmt.free();
    } catch (e) {
      console.error('Trade gap query failed:', e);
      return [];
    }

    // Group entry dates by (symbol, version, mode)
    const groups = new Map();
    const symbolDatesByMode = new Map();
    for (const r of rows) {
      const key = `${r.symbol}||${r.version}||${r.mode}`;
      if (!groups.has(key)) groups.set(key, { symbol: r.symbol, version: r.version, mode: r.mode, dates: [] });
      const raw = String(r.entry_time || '').trim();
      // Parse to a YYYY-MM-DD date string
      let dateStr = null;
      try {
        const d = new Date(raw.endsWith('Z') || raw.includes('+') ? raw : raw + 'Z');
        if (!isNaN(d.getTime())) dateStr = d.toISOString().slice(0, 10);
      } catch (_) {}
      if (!dateStr) {
        // Fallback: take first 10 chars if they look like a date
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

    // Compute max gap per symbol and per mode.
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

    return [...symbolBest.values()].sort((a, b) => {
      const aGap = a.combined ? a.combined.gap : -1;
      const bGap = b.combined ? b.combined.gap : -1;
      return bGap - aGap;
    });
  }

  function renderTradeGapModal() {
    const contentDiv = document.getElementById('tradeGapContent');
    if (!contentDiv) return;

    const results = computeTradeGapAnalysis();

    if (!results.length) {
      contentDiv.innerHTML = '<p style="color:var(--muted); padding:12px 0;">No backtest or paper trade data found.</p>';
      return;
    }

    const maxGap = Math.max(...results.map(r => (r.combined ? r.combined.gap : 0)), 0);
    const headerCells = [
      'Symbol',
      'Combined Gap',
      'Backtest Gap',
      'Paper Gap',
      'Latest Backtest Entry',
      'Latest Paper Entry',
      'Worst Gap Context',
    ]
      .map(h => `<th style="padding:8px 10px; text-align:${h.includes('Gap') ? 'right' : 'left'}; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.6px; border-bottom:1px solid var(--border); font-weight:600; white-space:nowrap;">${escapeHtml(h)}</th>`)
      .join('');

    const bodyRows = results.map(r => {
      const combined = r.combined;
      const backtest = r.backtest;
      const paper = r.paper;
      const combinedGap = combined ? combined.gap : null;
      const ratio = maxGap > 0 && combinedGap !== null ? combinedGap / maxGap : 0;
      const color = ratio > 0.7 ? 'var(--red)' : ratio > 0.4 ? 'var(--orange)' : 'var(--green)';
      const gapCell = g => (g ? `${g.gap}` : '-');
      const combinedText = combined ? `${combined.mode} ${combined.version} (${combined.from} -> ${combined.to})` : '-';
      return `<tr style="border-bottom:1px solid var(--border);">
        <td style="padding:8px 10px; font-weight:600; font-size:13px;">${escapeHtml(r.symbol)}</td>
        <td style="padding:8px 10px; text-align:right; font-weight:700; font-size:14px; color:${combinedGap !== null ? color : 'var(--muted)'};">${combinedGap !== null ? combinedGap : '-'}</td>
        <td style="padding:8px 10px; text-align:right; font-size:12px;">${gapCell(backtest)}</td>
        <td style="padding:8px 10px; text-align:right; font-size:12px;">${gapCell(paper)}</td>
        <td style="padding:8px 10px; font-size:12px; color:var(--muted);">${escapeHtml(r.latestBacktestEntry || '-')}</td>
        <td style="padding:8px 10px; font-size:12px; color:var(--muted);">${escapeHtml(r.latestPaperEntry || '-')}</td>
        <td style="padding:8px 10px; font-size:12px; color:var(--muted);">${escapeHtml(combinedText)}</td>
      </tr>`;
    }).join('');

    contentDiv.innerHTML = `
      <p style="font-size:12px; color:var(--muted); margin:0 0 12px 0;">
        Gaps are calendar days between consecutive entry dates. Combined Gap uses both backtest and paper rows.
        Backtest Gap and Paper Gap are computed independently so you can compare modes directly.
      </p>
      <table style="width:100%; border-collapse:collapse; font-size:13px;">
        <thead><tr>${headerCells}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>`;
  }

  function openTradeGapModal() {
    const modal = document.getElementById('tradeGapModal');
    if (!modal) return;
    renderTradeGapModal();
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeTradeGapModal() {
    const modal = document.getElementById('tradeGapModal');
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
  }

  // ── Guideline audit modal ───────────────────────────────────────────────────

  function _parseVersionFromSummary(metrics, notes) {
    const direct = String((metrics && metrics.version) || '').trim().toLowerCase();
    if (VERSION_KEYS.includes(direct)) return direct;
    const m = String(notes || '').match(/\b(v[1-6])\b/i);
    return m ? m[1].toLowerCase() : '';
  }

  function _getGuidelineOverride(symbol, version) {
    const key = `${getNormalizedSymbolKey(symbol)}|${String(version || '').toLowerCase()}`;
    return GUIDELINE_POLICY_OVERRIDES[key] || null;
  }

  function _evaluateGuidelineStatus(symbol, version, metrics) {
    const reasons = [];
    const waivedReasons = [];
    const override = _getGuidelineOverride(symbol, version);
    const advisoryOnly = new Set((override && override.advisoryOnly) || []);

    const checks = [
      {
        key: 'trades',
        failed: !Number.isFinite(metrics.trades) || metrics.trades < GUIDELINE_THRESHOLDS.minTrades,
        reason: `trades<${GUIDELINE_THRESHOLDS.minTrades}`,
      },
      {
        key: 'winRate',
        failed: !Number.isFinite(metrics.winRate) || metrics.winRate < GUIDELINE_THRESHOLDS.minWinRate,
        reason: `wr<${GUIDELINE_THRESHOLDS.minWinRate}`,
      },
      {
        key: 'netReturn',
        failed: !Number.isFinite(metrics.netReturn) || metrics.netReturn < GUIDELINE_THRESHOLDS.minNetReturn,
        reason: `net<${GUIDELINE_THRESHOLDS.minNetReturn}`,
      },
      {
        key: 'maxDrawdown',
        failed: !Number.isFinite(metrics.maxDrawdown) || metrics.maxDrawdown > GUIDELINE_THRESHOLDS.maxDrawdown,
        reason: `dd>${GUIDELINE_THRESHOLDS.maxDrawdown}`,
      },
    ];

    checks.forEach(check => {
      if (!check.failed) return;
      if (advisoryOnly.has(check.key)) {
        waivedReasons.push(`${check.reason} (advisory)`);
      } else {
        reasons.push(check.reason);
      }
    });

    if (reasons.length) {
      return {
        status: 'FAIL',
        reasons: reasons.concat(waivedReasons),
      };
    }

    if (waivedReasons.length) {
      return {
        status: 'CONDITIONAL',
        reasons: waivedReasons,
      };
    }

    return {
      status: 'PASS',
      reasons: [],
    };
  }

  function loadGuidelineAuditRowsFromDb() {
    const db = window._SQL_DB;
    if (!db) return [];

    const symbols = [];
    try {
      const stmt = db.prepare('SELECT symbol FROM symbols ORDER BY symbol');
      while (stmt.step()) {
        const row = stmt.getAsObject();
        symbols.push(String(row.symbol || '').trim());
      }
      stmt.free();
    } catch (err) {
      console.error('Failed loading symbols for guideline audit:', err);
      return [];
    }

    const latestBySymbolVersion = new Map();
    try {
      const stmt = db.prepare(`
        SELECT symbol, timestamp, metrics, notes, id
        FROM backtest_results
        ORDER BY datetime(timestamp) DESC, id DESC
      `);
      while (stmt.step()) {
        const row = stmt.getAsObject();
        let metrics = {};
        try {
          metrics = JSON.parse(String(row.metrics || '{}'));
        } catch (_) {
          metrics = {};
        }
        const symbol = String(row.symbol || '').trim();
        const version = _parseVersionFromSummary(metrics, row.notes);
        if (!symbol || !VERSION_KEYS.includes(version)) continue;
        const key = `${symbol}||${version}`;
        if (!latestBySymbolVersion.has(key)) {
          const trades = Number(metrics.total_trades);
          const winRate = Number.isFinite(Number(metrics.win_rate))
            ? Number(metrics.win_rate)
            : Number(metrics.win_rate_pct);
          const netReturn = Number(metrics.net_return_pct);

          let maxDrawdown = Number(metrics.max_drawdown_pct);
          if (!Number.isFinite(maxDrawdown)) {
            const ddAbs = Number(metrics.max_drawdown);
            const beginEq = Number(metrics.beginning_equity || metrics.initial_equity);
            if (Number.isFinite(ddAbs) && Number.isFinite(beginEq) && beginEq > 0) {
              maxDrawdown = (ddAbs / beginEq) * 100.0;
            }
          }

          latestBySymbolVersion.set(key, {
            symbol,
            version,
            timestamp: row.timestamp || null,
            trades,
            winRate,
            netReturn,
            maxDrawdown,
          });
        }
      }
      stmt.free();
    } catch (err) {
      console.error('Failed loading backtest summaries for guideline audit:', err);
      return [];
    }

    const rows = [];
    symbols.forEach(symbol => {
      VERSION_KEYS.forEach(version => {
        const found = latestBySymbolVersion.get(`${symbol}||${version}`);
        if (!found) {
          rows.push({
            symbol,
            version,
            timestamp: null,
            trades: null,
            winRate: null,
            netReturn: null,
            maxDrawdown: null,
            status: 'MISSING',
            reasons: ['no backtest summary row'],
          });
          return;
        }

        const evalResult = _evaluateGuidelineStatus(symbol, version, found);

        rows.push({
          symbol,
          version,
          timestamp: found.timestamp,
          trades: found.trades,
          winRate: found.winRate,
          netReturn: found.netReturn,
          maxDrawdown: found.maxDrawdown,
          status: evalResult.status,
          reasons: evalResult.reasons,
        });
      });
    });

    return rows;
  }

  async function loadGuidelineAuditRows() {
    const matrixPaths = ['data/guideline_matrix_all_versions.json', 'docs/data/guideline_matrix_all_versions.json'];
    for (const matrixPath of matrixPaths) {
      try {
        const req = await fetch(`${matrixPath}?v=${Date.now()}`);
        if (!req.ok) continue;
        const payload = await req.json();
        const records = Array.isArray(payload && payload.records) ? payload.records : [];
        if (!records.length) continue;

        return records
          .map(rec => {
            const symbol = String(rec.symbol || '').trim();
            const version = String(rec.version || '').trim().toLowerCase();
            if (!symbol || !VERSION_KEYS.includes(version)) return null;

            const reasons = Array.isArray(rec.reasons)
              ? rec.reasons.map(r => String(r || '').trim()).filter(Boolean)
              : [];
            const hasHardFailures = reasons.some(r => !r.toLowerCase().endsWith('(advisory)'));
            let status = 'PASS';
            if (rec.pass_all === false || hasHardFailures) status = 'FAIL';
            else if (reasons.length) status = 'CONDITIONAL';

            return {
              symbol,
              version,
              timestamp: rec.timestamp || null,
              trades: Number(rec.trades),
              winRate: Number(rec.win_rate_pct),
              netReturn: Number(rec.net_return_pct),
              maxDrawdown: Number(rec.max_drawdown_pct),
              status,
              reasons,
            };
          })
          .filter(Boolean);
      } catch (err) {
        console.warn('Failed loading guideline matrix JSON for audit:', err);
      }
    }

    return loadGuidelineAuditRowsFromDb();
  }

  async function renderGuidelineAuditModal() {
    const content = document.getElementById('guidelineAuditContent');
    const meta = document.getElementById('guidelineAuditMeta');
    if (!content || !meta) return;

    content.innerHTML = '<p style="color:var(--muted);">Loading guideline audit...</p>';
    const rows = await loadGuidelineAuditRows();
    _cachedAuditRows = rows;

    // Reset to status tab on fresh open
    switchGuidelineAuditTab('status');

    if (!rows.length) {
      meta.textContent = 'No symbols or backtest summaries found.';
      content.innerHTML = '<p style="color:var(--muted);">No guideline data available.</p>';
      return;
    }

    const passCount = rows.filter(r => r.status === 'PASS').length;
    const conditionalCount = rows.filter(r => r.status === 'CONDITIONAL').length;
    const failCount = rows.filter(r => r.status === 'FAIL').length;
    const missingCount = rows.filter(r => r.status === 'MISSING').length;
    meta.textContent = `Thresholds: trades>=${GUIDELINE_THRESHOLDS.minTrades}, win_rate>=${GUIDELINE_THRESHOLDS.minWinRate}%, net_return>=${GUIDELINE_THRESHOLDS.minNetReturn}%, max_drawdown<=${GUIDELINE_THRESHOLDS.maxDrawdown}% | PASS ${passCount} | CONDITIONAL ${conditionalCount} | FAIL ${failCount} | MISSING ${missingCount} | policy overrides applied`;

    const sorted = rows.slice().sort((a, b) => {
      const s = a.symbol.localeCompare(b.symbol);
      if (s !== 0) return s;
      return a.version.localeCompare(b.version);
    });

    const fmtMetric = (n, digits = 2) => (Number.isFinite(Number(n)) ? Number(n).toFixed(digits) : '-');
    const statusBadge = status => {
      if (status === 'PASS') return '<span class="tag tag-tp">PASS</span>';
      if (status === 'CONDITIONAL') return '<span class="tag" style="background:#f59e0b22;color:#f59e0b;border-color:#f59e0b66;">CONDITIONAL</span>';
      if (status === 'FAIL') return '<span class="tag tag-sl">FAIL</span>';
      return '<span class="tag tag-other">MISSING</span>';
    };

    const bodyRows = sorted.map(r => {
      const action = (r.status === 'PASS' || r.status === 'CONDITIONAL')
        ? '<span style="color:var(--muted);">-</span>'
        : `<button type="button" class="mode-btn guideline-rerun-btn" data-symbol="${escapeHtml(r.symbol)}" data-version="${escapeHtml(r.version)}">Rerun ${escapeHtml(r.version.toUpperCase())}</button>`;
      const reasonsText = r.reasons && r.reasons.length ? r.reasons.join(', ') : '-';
      return `<tr style="border-bottom:1px solid var(--border);">
        <td style="padding:8px 10px; font-weight:600;">${escapeHtml(r.symbol)}</td>
        <td style="padding:8px 10px;"><span class="pill" style="background:#58a6ff22;color:var(--accent);border-color:#58a6ff44;">${escapeHtml(r.version.toUpperCase())}</span></td>
        <td style="padding:8px 10px; text-align:right;">${fmtMetric(r.trades, 0)}</td>
        <td style="padding:8px 10px; text-align:right;">${fmtMetric(r.winRate)}</td>
        <td style="padding:8px 10px; text-align:right;">${fmtMetric(r.netReturn)}</td>
        <td style="padding:8px 10px; text-align:right;">${fmtMetric(r.maxDrawdown)}</td>
        <td style="padding:8px 10px;">${statusBadge(r.status)}</td>
        <td style="padding:8px 10px; color:var(--muted);">${escapeHtml(reasonsText)}</td>
        <td style="padding:8px 10px; text-align:right;">${action}</td>
      </tr>`;
    }).join('');

    content.innerHTML = `
      <table style="width:100%; border-collapse:collapse; font-size:12px;">
        <thead>
          <tr style="border-bottom:1px solid var(--border);">
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Symbol</th>
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Version</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">Trades</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">WR%</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">Net%</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">MaxDD%</th>
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Status</th>
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Reasons</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">Action</th>
          </tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>`;
  }

  async function openGuidelineAuditModal() {
    const modal = document.getElementById('guidelineAuditModal');
    if (!modal) return;
    await renderGuidelineAuditModal();
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeGuidelineAuditModal() {
    const modal = document.getElementById('guidelineAuditModal');
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
  }

  // ── Guideline vs. Dashboard Data comparison ────────────────────────────────

  let _guidelineAuditView = 'status'; // 'status' | 'compare'
  let _cachedAuditRows = null;

  async function loadDashboardDataJsons() {
    const btPaths = ['data/backtest_results.json', 'docs/data/backtest_results.json'];
    const ptPaths = ['data/paper_trading_results.json', 'docs/data/paper_trading_results.json'];

    const fetchFirst = async (paths) => {
      for (const p of paths) {
        try {
          const r = await fetch(`${p}?v=${Date.now()}`);
          if (r.ok) return await r.json();
        } catch (_) { /* try next */ }
      }
      return null;
    };

    const [btRaw, ptRaw] = await Promise.all([fetchFirst(btPaths), fetchFirst(ptPaths)]);

    // Build (symbol, version) → row lookup for backtest
    const btLookup = new Map();
    if (btRaw && typeof btRaw === 'object') {
      for (const [sym, versObj] of Object.entries(btRaw)) {
        if (!versObj || typeof versObj !== 'object') continue;
        for (const [ver, rows] of Object.entries(versObj)) {
          const row = Array.isArray(rows) ? rows[0] : null;
          if (row) btLookup.set(`${sym}||${ver}`, row);
        }
      }
    }

    // Build (symbol, version) → row lookup for paper trading
    const ptLookup = new Map();
    if (ptRaw && typeof ptRaw === 'object') {
      if (Array.isArray(ptRaw)) {
        for (const row of ptRaw) {
          if (row && row.symbol && row.version) ptLookup.set(`${row.symbol}||${row.version}`, row);
        }
      } else {
        for (const [sym, rows] of Object.entries(ptRaw)) {
          const list = Array.isArray(rows) ? rows : Object.values(rows);
          for (const row of list) {
            if (row && row.version) ptLookup.set(`${sym}||${row.version}`, row);
          }
        }
      }
    }

    return { btLookup, ptLookup };
  }

  async function renderGuidelineCompareTable(auditRows) {
    const el = document.getElementById('guidelineCompareContent');
    if (!el) return;
    el.innerHTML = '<p style="color:var(--muted); padding:12px;">Loading dashboard data...</p>';

    const { btLookup, ptLookup } = await loadDashboardDataJsons();

    const fmtN = (n, d = 2) => Number.isFinite(Number(n)) ? Number(n).toFixed(d) : '-';
    const fmtDelta = (d, thresh) => {
      if (!Number.isFinite(d)) return '<td class="gca-delta">-</td>';
      const abs = Math.abs(d);
      const style = abs > thresh
        ? 'color:#f85149; font-weight:600;'
        : abs > thresh / 4
          ? 'color:#f59e0b;'
          : 'color:var(--muted);';
      const sign = d >= 0 ? '+' : '';
      return `<td class="gca-delta" style="${style}">${sign}${d.toFixed(2)}</td>`;
    };

    const sorted = auditRows.slice().sort((a, b) => {
      const s = a.symbol.localeCompare(b.symbol);
      return s !== 0 ? s : a.version.localeCompare(b.version);
    });

    const sourceTag = (label, color) =>
      `<span style="display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;background:${color}22;color:${color};border:1px solid ${color}66;">${label}</span>`;

    let rows = '';
    let prevSym = '';
    for (const r of sorted) {
      const key = `${r.symbol}||${r.version}`;
      const bt = btLookup.get(key);
      const pt = ptLookup.get(key);

      const borderTop = r.symbol !== prevSym ? 'border-top:2px solid var(--border);' : '';
      prevSym = r.symbol;

      // ── Guideline row
      const gmTrades = Number(r.trades);
      const gmWR = Number(r.winRate);
      const gmNet = Number(r.netReturn);
      const gmDD = Number(r.maxDrawdown);
      const statusBadge = r.status === 'PASS'
        ? '<span class="tag tag-tp">PASS</span>'
        : r.status === 'CONDITIONAL'
          ? '<span class="tag" style="background:#f59e0b22;color:#f59e0b;border-color:#f59e0b66;">COND</span>'
          : r.status === 'FAIL'
            ? '<span class="tag tag-sl">FAIL</span>'
            : '<span class="tag tag-other">MISSING</span>';

      rows += `<tr style="${borderTop}">
        <td rowspan="${1 + (bt ? 1 : 0) + (pt ? 1 : 0)}" style="padding:6px 10px; font-weight:600; vertical-align:top;">${escapeHtml(r.symbol)}</td>
        <td rowspan="${1 + (bt ? 1 : 0) + (pt ? 1 : 0)}" style="padding:6px 10px; vertical-align:top;"><span class="pill" style="background:#58a6ff22;color:var(--accent);border-color:#58a6ff44;">${escapeHtml(r.version.toUpperCase())}</span></td>
        <td class="gca-src">${sourceTag('Guideline', '#58a6ff')}</td>
        <td class="gca-num">${fmtN(gmTrades, 0)}</td>
        <td class="gca-num">${fmtN(gmWR)}</td>
        <td class="gca-num">${fmtN(gmNet)}</td>
        <td class="gca-num">${fmtN(gmDD)}</td>
        <td class="gca-delta">-</td>
        <td class="gca-delta">-</td>
        <td class="gca-delta">-</td>
        <td class="gca-delta">-</td>
        <td style="padding:6px 10px;">${statusBadge}</td>
      </tr>`;

      // ── Backtest row
      if (bt) {
        const beginEq = Number(bt.beginning_equity || 0);
        const btMdd = beginEq > 0 ? (Number(bt.max_drawdown) / beginEq * 100) : Number(bt.max_drawdown);
        const btTrades = Number(bt.total_trades);
        const btWR = Number(bt.win_rate);
        const btNet = Number(bt.net_return_pct);
        const dTr = Number.isFinite(gmTrades) && Number.isFinite(btTrades) ? gmTrades - btTrades : NaN;
        const dWR = Number.isFinite(gmWR) && Number.isFinite(btWR) ? gmWR - btWR : NaN;
        const dNet = Number.isFinite(gmNet) && Number.isFinite(btNet) ? gmNet - btNet : NaN;
        const dDD = Number.isFinite(gmDD) && Number.isFinite(btMdd) ? gmDD - btMdd : NaN;
        rows += `<tr>
          <td class="gca-src">${sourceTag('Backtest', '#3fb950')}</td>
          <td class="gca-num">${fmtN(btTrades, 0)}</td>
          <td class="gca-num">${fmtN(btWR)}</td>
          <td class="gca-num">${fmtN(btNet)}</td>
          <td class="gca-num">${fmtN(btMdd)}</td>
          ${fmtDelta(dTr, 2)}
          ${fmtDelta(dWR, 2)}
          ${fmtDelta(dNet, 2)}
          ${fmtDelta(dDD, 1)}
          <td style="padding:6px 10px;"></td>
        </tr>`;
      }

      // ── Paper trading row
      if (pt) {
        const beginEq = Number(pt.beginning_equity || 0);
        const ptMdd = beginEq > 0 ? (Number(pt.max_drawdown) / beginEq * 100) : Number(pt.max_drawdown);
        const ptTrades = Number(pt.total_trades);
        const ptWR = Number(pt.win_rate);
        const ptNet = Number(pt.net_return_pct);
        const dTr = Number.isFinite(gmTrades) && Number.isFinite(ptTrades) ? gmTrades - ptTrades : NaN;
        const dWR = Number.isFinite(gmWR) && Number.isFinite(ptWR) ? gmWR - ptWR : NaN;
        const dNet = Number.isFinite(gmNet) && Number.isFinite(ptNet) ? gmNet - ptNet : NaN;
        const dDD = Number.isFinite(gmDD) && Number.isFinite(ptMdd) ? gmDD - ptMdd : NaN;
        rows += `<tr>
          <td class="gca-src">${sourceTag('Paper', '#f59e0b')}</td>
          <td class="gca-num">${fmtN(ptTrades, 0)}</td>
          <td class="gca-num">${fmtN(ptWR)}</td>
          <td class="gca-num">${fmtN(ptNet)}</td>
          <td class="gca-num">${fmtN(ptMdd)}</td>
          ${fmtDelta(dTr, 2)}
          ${fmtDelta(dWR, 2)}
          ${fmtDelta(dNet, 2)}
          ${fmtDelta(dDD, 1)}
          <td style="padding:6px 10px;"></td>
        </tr>`;
      }
    }

    // Count rows with significant mismatches
    let mismatchCount = 0;
    for (const r of sorted) {
      const key = `${r.symbol}||${r.version}`;
      const bt = btLookup.get(key);
      if (!bt) continue;
      const beginEq = Number(bt.beginning_equity || 0);
      const btMdd = beginEq > 0 ? (Number(bt.max_drawdown) / beginEq * 100) : Number(bt.max_drawdown);
      const dTr = Math.abs(Number(r.trades) - Number(bt.total_trades));
      const dNet = Math.abs(Number(r.netReturn) - Number(bt.net_return_pct));
      const dDD = Math.abs(Number(r.maxDrawdown) - btMdd);
      if (dTr > 2 || dNet > 2 || dDD > 1) mismatchCount++;
    }

    const metaEl = document.getElementById('guidelineAuditMeta');
    if (metaEl) {
      metaEl.textContent = `Comparing guideline matrix vs. backtest_results.json & paper_trading_results.json. ${mismatchCount} of ${sorted.length} symbol/version combos have significant discrepancies (|trades|>2, |net%|>2, or |mdd%|>1). Delta columns show: Guideline minus Dashboard source.`;
    }

    el.innerHTML = `
      <style>
        .gca-src { padding: 5px 10px; }
        .gca-num { padding: 5px 10px; text-align: right; font-variant-numeric: tabular-nums; }
        .gca-delta { padding: 5px 10px; text-align: right; font-variant-numeric: tabular-nums; }
      </style>
      <table style="width:100%; border-collapse:collapse; font-size:12px;">
        <thead>
          <tr style="border-bottom:2px solid var(--border); position:sticky; top:0; background:var(--card-bg, #161b22);">
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Symbol</th>
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Ver</th>
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Source</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">Trades</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">WR%</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">Net%</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">MaxDD%</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">dTrades</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">dWR</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">dNet%</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">dDD%</th>
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Status</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function switchGuidelineAuditTab(tab) {
    _guidelineAuditView = tab;
    const statusContent = document.getElementById('guidelineAuditContent');
    const compareContent = document.getElementById('guidelineCompareContent');
    const statusBtn = document.getElementById('guidelineTabStatus');
    const compareBtn = document.getElementById('guidelineTabCompare');
    if (!statusContent || !compareContent) return;

    const showStatus = tab === 'status';
    statusContent.style.display = showStatus ? '' : 'none';
    compareContent.style.display = showStatus ? 'none' : '';
    statusBtn && statusBtn.classList.toggle('active', showStatus);
    compareBtn && compareBtn.classList.toggle('active', !showStatus);

    if (!showStatus && _cachedAuditRows) {
      renderGuidelineCompareTable(_cachedAuditRows);
    }
  }

  // ── Live Symbol Control modal ──────────────────────────────────────────────

  function loadLiveSymbolControlRows() {
    const db = window._SQL_DB;
    if (!db) return [];

    let hasLiveEnabled = false;
    try {
      const info = db.exec('PRAGMA table_info(symbols)');
      const cols = (info[0] && info[0].values ? info[0].values : []).map(row => String(row[1] || ''));
      hasLiveEnabled = cols.includes('live_enabled');
    } catch (e) {
      console.warn('Could not inspect symbols schema:', e);
    }

    const query = hasLiveEnabled
      ? 'SELECT symbol, description, COALESCE(live_enabled, 1) AS live_enabled FROM symbols ORDER BY symbol'
      : 'SELECT symbol, description, 1 AS live_enabled FROM symbols ORDER BY symbol';

    const out = [];
    try {
      const stmt = db.prepare(query);
      while (stmt.step()) {
        const row = stmt.getAsObject();
        out.push({
          symbol: String(row.symbol || ''),
          description: String(row.description || ''),
          live_enabled: Number(row.live_enabled || 0) === 1,
        });
      }
      stmt.free();
    } catch (e) {
      console.error('Failed loading symbols for live control modal:', e);
    }
    return out;
  }

  function buildLiveToggleIssueUrl(symbol, targetEnabled, currentEnabled) {
    const desired = targetEnabled ? 'true' : 'false';
    const desiredLabel = targetEnabled ? 'ENABLED' : 'DISABLED';
    const title = encodeURIComponent(`Live Trading Toggle: ${symbol} -> ${desiredLabel}`);
    const body = encodeURIComponent(
      `Symbol: ${symbol}\n` +
      `Live Enabled: ${desired}\n` +
      `Current Enabled (dashboard snapshot): ${currentEnabled ? 'true' : 'false'}\n\n` +
      `_Requested from dashboard Live Symbol Control modal._`
    );
    return `https://github.com/rcaldwell67/pinescripts/issues/new?title=${title}&body=${body}&labels=toggle-live-symbol`;
  }

  function buildRerunAllBacktestsIssueUrl(symbol) {
    const normalizedSymbol = String(symbol || '').trim().toUpperCase();
    const title = encodeURIComponent(`Rerun Backtest: ${normalizedSymbol} V6`);
    const body = encodeURIComponent(
      `Symbol: ${normalizedSymbol}\n` +
      `Version: v6\n\n` +
      `_Requested from dashboard Rerun All Versions button._`
    );
    return `https://github.com/rcaldwell67/pinescripts/issues/new?title=${title}&body=${body}`;
  }

  function renderLiveSymbolControlModal() {
    const content = document.getElementById('liveSymbolControlContent');
    if (!content) return;

    const rows = loadLiveSymbolControlRows();
    if (!rows.length) {
      content.innerHTML = '<p style="color:var(--muted);">No symbols found in DB.</p>';
      return;
    }

    const bodyRows = rows.map(r => {
      const state = r.live_enabled ? 'Enabled' : 'Disabled';
      const stateClass = r.live_enabled ? 'is-fresh' : 'is-stale';
      const nextEnabled = !r.live_enabled;
      const actionLabel = nextEnabled ? 'Enable' : 'Disable';
      return `<tr style="border-bottom:1px solid var(--border);">
        <td style="padding:8px 10px; font-weight:600;">${escapeHtml(r.symbol)}</td>
        <td style="padding:8px 10px; color:var(--muted);">${escapeHtml(r.description || '-')}</td>
        <td style="padding:8px 10px;"><span class="snapshot-age ${stateClass}">${escapeHtml(state)}</span></td>
        <td style="padding:8px 10px; text-align:right;">
          <button type="button" class="mode-btn live-toggle-btn" data-symbol="${escapeHtml(r.symbol)}" data-target-enabled="${nextEnabled ? '1' : '0'}" data-current-enabled="${r.live_enabled ? '1' : '0'}">${actionLabel}</button>
        </td>
      </tr>`;
    }).join('');

    content.innerHTML = `
      <p style="font-size:12px; color:var(--muted); margin:0 0 12px 0;">
        This dashboard opens an issue to apply each symbol toggle through CI automation.
        Changes are committed to the DB, then used automatically by the live trading runner when it runs with --all-symbols.
      </p>
      <table style="width:100%; border-collapse:collapse; font-size:12px;">
        <thead>
          <tr style="border-bottom:1px solid var(--border);">
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Symbol</th>
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Description</th>
            <th style="padding:8px 10px; text-align:left; color:var(--muted);">Live Trading</th>
            <th style="padding:8px 10px; text-align:right; color:var(--muted);">Action</th>
          </tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>`;
  }

  function openLiveSymbolControlModal() {
    const modal = document.getElementById('liveSymbolControlModal');
    if (!modal) return;
    renderLiveSymbolControlModal();
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeLiveSymbolControlModal() {
    const modal = document.getElementById('liveSymbolControlModal');
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
  }

  function getActiveRows() {
    const raw = activeTab === 'all'
      ? Object.values(loaded[activeSym] || {}).flat()
      : (loaded[activeSym]?.[activeTab] || []);
    return filterPaperRows(raw);
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
    const versionConfigs = INSTRUMENTS[activeSym]?.versions || {};
    const hasVariants = Object.values(versionConfigs).some(cfg => Boolean(cfg && cfg.backtestVariants));
    const show = activeMode === 'backtest' && hasVariants;
    if (wrap) wrap.style.display = show ? 'flex' : 'none';
    if (show) {
      for (const version of VERSION_KEYS) {
        const select = document.getElementById(`${version}DatasetSelect`);
        if (!select) continue;
        const cfg = versionConfigs[version];
        if (!cfg || !cfg.backtestVariants) continue;
        select.value = getSelectedBacktestVariant(activeSym, version);
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
  const rerunAllBtnId = 'rerunAllVersionsWorkflowBtn';
  let rerunBtn = document.getElementById(rerunBtnId);
  let rerunAllBtn = document.getElementById(rerunAllBtnId);
  const shouldShowBacktest = activeTab !== 'all' && activeDataset === 'backtest';
  const shouldShowPaper = activeTab !== 'all' && activeDataset === 'paper' && PAPER_TRADING_SUPPORTED_VERSIONS.has(activeTab);
  const shouldShowLive = activeTab !== 'all' && activeDataset === 'live' && LIVE_TRADING_SUPPORTED_VERSIONS.has(activeTab);
  const shouldShowAllBacktest = activeTab === 'all' && activeDataset === 'backtest' && Boolean(activeSym);
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

  if (shouldShowAllBacktest) {
    if (!rerunAllBtn) {
      rerunAllBtn = document.createElement('button');
      rerunAllBtn.id = rerunAllBtnId;
      rerunAllBtn.style = 'margin-left:16px;padding:6px 18px;border-radius:6px;border:1px solid var(--accent);background:var(--accent);color:#fff;font-size:13px;font-weight:600;cursor:pointer;';
      tabEl.appendChild(rerunAllBtn);
    }
    rerunAllBtn.textContent = 'Rerun All Versions';
    rerunAllBtn.onclick = function() {
      rerunAllBacktests(activeSym);
    };
    tabEl.appendChild(rerunAllBtn);
    rerunAllBtn.style.display = '';
  } else if (rerunAllBtn) {
    rerunAllBtn.style.display = 'none';
  }
}
function openWorkflowIssue(workflowType, symbol, version, options = {}) {
  const sym = symbol.toUpperCase();
  const ver = version.toUpperCase();
  const isPaper = workflowType === 'paper';
  const isLive = workflowType === 'live';
  const workflowLabel = isLive ? 'Live Trading' : (isPaper ? 'Paper Trading' : 'Backtest');
  const issueTitle = encodeURIComponent(`Rerun ${workflowLabel}: ${sym} ${ver}`);
  const executionMode = String(options.executionMode || 'realtime').toLowerCase() === 'simulation'
    ? 'simulation'
    : 'realtime';
  const simulationDataScope = String(options.simulationDataScope || 'historical').toLowerCase() === 'same_day'
    ? 'same_day'
    : 'historical';
  const bodyLines = [
    `Please rerun ${isLive ? 'live trading' : (isPaper ? 'paper trading' : 'the backtest')} for ${sym} version ${ver}.`,
  ];
  if (isPaper) {
    bodyLines.push('');
    bodyLines.push(`Execution Mode: ${executionMode}`);
    bodyLines.push(`Simulation Data Scope: ${simulationDataScope}`);
    if (executionMode === 'simulation' && simulationDataScope === 'same_day') {
      bodyLines.push('Force Reset: true');
    }
    bodyLines.push('Prefer Realtime Data: true');
    bodyLines.push('Realtime Only Data: true');
  }
  bodyLines.push('');
  bodyLines.push('_This request was generated from the dashboard UI._');
  const issueBody = encodeURIComponent(bodyLines.join('\n'));
  const url = `https://github.com/rcaldwell67/pinescripts/issues/new?title=${issueTitle}&body=${issueBody}`;
  window.open(url, '_blank');
  updateWorkflowStatus(`${workflowLabel} rerun requested for ${sym} ${ver}. Submit the opened GitHub issue form to start the workflow.`, '#58a6ff');
}

function rerunBacktest(symbol, version) {
  openWorkflowIssue('backtest', symbol, version);
}

function rerunPaperTrading(symbol, version) {
  const executionMode = paperTradeSourceFilter === 'simulation' ? 'simulation' : 'realtime';
  openWorkflowIssue('paper', symbol, version, {
    executionMode,
    simulationDataScope: simulationDataScopeFilter,
  });
}

function rerunLiveTrading(symbol, version) {
  openWorkflowIssue('live', symbol, version);
}

function rerunAllBacktests(symbol) {
  if (!symbol) return;
  const confirmed = confirm(
    `Create a GitHub issue to rerun v6 for "${symbol}"?\n\n` +
    `This triggers the Rerun Backtest workflow via issue automation.`
  );
  if (!confirmed) return;
  const url = buildRerunAllBacktestsIssueUrl(symbol);
  window.open(url, '_blank');
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
    const finalEquity = Number(s.current_equity || s.final_equity || beginEq);
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

function getTotalEquityAllVersionsAllSymbols() {
  const db = window._SQL_DB;
  if (!db) return null;
  if (activeDataset !== 'backtest') {
    return { total: getDatasetInitialCapital(), buckets: 0 };
  }
  try {
    const stmt = db.prepare(`
      WITH latest AS (
        SELECT
          symbol,
          version,
          equity,
          ROW_NUMBER() OVER (
            PARTITION BY REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', ''), LOWER(version)
            ORDER BY datetime(COALESCE(exit_time, entry_time)) DESC, id DESC
          ) AS rn
        FROM trades
        WHERE mode = 'backtest' AND equity IS NOT NULL AND LOWER(version) IN ('v6')
      )
      SELECT COALESCE(SUM(equity), 0) AS total_equity, COUNT(*) AS buckets
      FROM latest
      WHERE rn = 1
    `);
    let total = 0;
    let buckets = 0;
    if (stmt.step()) {
      const row = stmt.getAsObject();
      total = Number(row.total_equity || 0);
      buckets = Number(row.buckets || 0);
    }
    stmt.free();
    return { total, buckets };
  } catch (err) {
    console.error('Error querying total equity across all symbols/versions:', err);
    return null;
  }
}

function renderCards(rows) {
  const cardEl = document.getElementById('cards');
  const vers = INSTRUMENTS[activeSym].versions;
  const totalEq = getTotalEquityAllVersionsAllSymbols();
  const totalEqCard = totalEq
    ? `<div class="card">
        <div class="label">Total Equity (All Versions, All Symbols)</div>
        <div class="value neutral">${fmt$(totalEq.total)}</div>
        <div class="sub">${activeDataset === 'backtest' ? `Latest equity snapshot across ${totalEq.buckets} v1-v6 symbol-version buckets` : 'Baseline starting equity for this dataset'}</div>
      </div>`
    : '';
  if (activeTab === 'all') {
    cardEl.innerHTML = totalEqCard + Object.entries(vers).map(([v,cfg])=>{
      const r = filterPaperRows(loaded[activeSym][v] || []);
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
  const datasetBalance = getDatasetCurrentBalance();
  const displayCurrentEq = Number.isFinite(datasetBalance && datasetBalance.value)
    ? datasetBalance.value
    : m.finalEquity;
  const snapshotTime = datasetBalance && datasetBalance.updatedAt
    ? datasetBalance.updatedAt
    : getLatestEquityTimestampFromRows(rows);
  const snapshotLabel = snapshotTime ? formatTickerTimestamp(snapshotTime) : 'unknown';
  const snapshotAge = getSnapshotAgeInfo(snapshotTime);
  const sourceLabel = datasetBalance && datasetBalance.source === 'account'
    ? `${activeDataset} account`
    : `${activeDataset} trades`;
  const currentEqSub = `${sourceLabel} snapshot ${snapshotLabel} <span class="snapshot-age ${snapshotAge.state}">${snapshotAge.label}</span> - Started $${m.beginEq.toLocaleString()}`;
  cardEl.innerHTML = `
    ${totalEqCard}
    <div class="card"><div class="label">Total Trades</div><div class="value neutral">${m.n}</div><div class="sub">${m.longs}L / ${m.shorts}S</div></div>
      <div class="card"><div class="label">Win Rate</div><div class="value ${m.winRate>=70?'positive':m.winRate>=60?'neutral':'negative'}">${m.winRate.toFixed(1)}%</div><div class="sub">Target ≥70% · ${m.tpCount} TP - ${m.slCount} SL - ${m.trailCount} Trail${m.mbCount?' - '+m.mbCount+' MB':''}</div></div>
    <div class="card"><div class="label">Net P&L</div><div class="value ${clsVal(m.netPnl)}">${fmt$(m.netPnl)}</div><div class="sub">${fmtPct(m.netPnlPct)} on $${m.beginEq.toLocaleString()}</div></div>
    <div class="card"><div class="label">Profit Factor</div><div class="value ${m.pf>=2?'positive':m.pf>=1?'neutral':'negative'}">${fmtPF(m.pf, 3)}</div><div class="sub">Gross Win / Gross Loss</div></div>
      <div class="card"><div class="label">Max Drawdown</div><div class="value ${m.maxDD<4.5?'positive':m.maxDD<10?'neutral':'negative'}">-${m.maxDD.toFixed(2)}%</div><div class="sub">Target ≤4.5% · Peak-to-trough</div></div>
    <div class="card"><div class="label">Current Equity</div><div class="value ${clsVal(displayCurrentEq-m.beginEq)}">$${displayCurrentEq.toFixed(2)}</div><div class="sub">${currentEqSub}</div></div>`;
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
      const r = filterPaperRows(loaded[activeSym][v] || []);
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
  const all = activeTab==='all' ? filterPaperRows(Object.values(loaded[activeSym]).flat()) : rows;
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
    const vkeys=Object.keys(vers).filter(v=>filterPaperRows(loaded[activeSym][v]||[]).length);
    const labels=vkeys.map(v=>vers[v].tf), wrs=vkeys.map(v=>calcMetrics(filterPaperRows(loaded[activeSym][v]||[]))?.winRate??0);
    const pnls=vkeys.map(v=>calcMetrics(filterPaperRows(loaded[activeSym][v]||[]))?.netPnlPct??0), colors=vkeys.map(v=>vers[v].color);
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
  const src=activeTab==='all'?filterPaperRows(Object.values(loaded[activeSym]).flat()):rows;
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
    :Object.keys(vers).find(v=>vers[v].hasYear&&filterPaperRows(loaded[activeSym][v]||[]).length);
  if (!verKey) return;
  const rows=filterPaperRows(loaded[activeSym][verKey] || []), cfg=vers[verKey];
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
  const realtimeStatusEl = document.getElementById('tradeRealtimeStatus');
  const isPaperMode = activeDataset === 'paper';

  const displayRows = Array.isArray(rows) ? rows : [];

  if (realtimeStatusEl) {
    if (!isPaperMode) {
      realtimeStatusEl.style.display = 'none';
      realtimeStatusEl.textContent = '';
    } else {
      const now = new Date();
      const monthStartMs = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1, 0, 0, 0, 0);
      let realtimeMtd = 0;
      let simulationMtd = 0;
      let lastRealtimeTs = 0;
      const fillStats = getPaperFillStats(activeSym, monthStartMs);

      // Always count MTD from all loaded rows regardless of active source filter
      Object.values(loaded[activeSym] || {}).flat().forEach(r => {
        const ts = parseDashboardTimeValue(r.exit_time || r.entry_time);
        if (!ts || ts < monthStartMs) return;
        if (normalizeSource(r.source) === 'realtime') {
          realtimeMtd += 1;
          if (ts > lastRealtimeTs) lastRealtimeTs = ts;
        } else {
          simulationMtd += 1;
        }
      });

      if (realtimeMtd > 0) {
        const lastLabel = new Date(lastRealtimeTs).toLocaleString('en-US', {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        });
        realtimeStatusEl.textContent = `Realtime paper active this month (${realtimeMtd} trades, fills: ${fillStats.mtdCount}, last ${lastLabel})`;
        realtimeStatusEl.style.color = '#3fb950';
      } else {
        const lastFillLabel = fillStats.lastTs > 0
          ? new Date(fillStats.lastTs).toLocaleString('en-US', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })
          : 'none';
        realtimeStatusEl.textContent = `Realtime paper inactive this month (fills: ${fillStats.mtdCount}, simulation trades: ${simulationMtd}, last fill: ${lastFillLabel})`;
        realtimeStatusEl.style.color = '#ffa657';
      }
      realtimeStatusEl.style.display = '';
    }
  }

  if (!displayRows.length) {
    const label = isPaperMode
      ? (paperTradeSourceFilter === 'realtime' ? 'No realtime paper trades for this selection' : paperTradeSourceFilter === 'simulation' ? 'No simulation paper trades for this selection' : 'No paper trades for this selection')
      : 'No data';
    wrap.innerHTML = `<div class="empty">${label}</div>`;
    return;
  }

  const showVer = activeTab === 'all';
  const showSource = isPaperMode;
  const vers = INSTRUMENTS[activeSym].versions;
  const sorted = displayRows.slice().sort((a, b) => {
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
    <th scope="col">Entry</th><th scope="col">Exit</th><th scope="col">Dir</th>${showSource ? '<th scope="col">Source</th>' : ''}<th scope="col">Entry $</th><th scope="col">Exit $</th><th scope="col">P&L</th><th scope="col">Result</th><th scope="col">Equity</th>
  </tr></thead><tbody>${paged.map(r => {
    const dirTag = r.direction === 'long' ? 'tag-long' : 'tag-short';
    const cfg = vers[r.version];
    const src = normalizeSource(r.source);
    const sourceTag = showSource
      ? (src === 'realtime'
        ? '<span class="tag tag-tp">realtime</span>'
        : '<span class="tag tag-other">simulation</span>')
      : '';
    const ep = r.entry_price < 100 ? '$' + r.entry_price?.toFixed(4) : '$' + r.entry_price?.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
    const xp = r.exit_price  < 100 ? '$' + r.exit_price?.toFixed(4)  : '$' + r.exit_price?.toLocaleString('en-US',  {minimumFractionDigits:2, maximumFractionDigits:2});
    return `<tr>
      ${showVer ? `<td><span class="pill" style="background:${cfg.color}22;color:${cfg.color};border-color:${cfg.color}">${cfg.tf}</span></td>` : ''}
      <td>${fmtDate(r.entry_time)}</td><td>${fmtDate(r.exit_time)}</td>
      <td><span class="tag ${dirTag}">${r.direction || '-'}</span></td>
      ${showSource ? `<td>${sourceTag}</td>` : ''}
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

function toEpochMs(value) {
  if (!value) return 0;
  const t = new Date(String(value).replace(' ', 'T')).getTime();
  return Number.isFinite(t) ? t : 0;
}

function getActiveSymbolKeys() {
  const keys = new Set();
  if (!activeSym) return keys;
  const aliases = getSymbolAliases(activeSym);
  aliases.forEach(alias => {
    const normalized = getNormalizedSymbolKey(alias);
    if (normalized) keys.add(normalized);
  });
  const activeKey = getNormalizedSymbolKey(activeSym);
  if (activeKey) keys.add(activeKey);
  return keys;
}

function decodeLogSourceLabel(source) {
  if (source === 'diagnostic') return 'Diagnostic JSONL';
  if (source === 'nearmiss') return 'Near Misses';
  if (source === 'runhistory') return 'Run History';
  if (source === 'summary') return 'Realtime Summary';
  if (source === 'fills') return 'Paper Fill Event';
  if (source === 'orders') return 'Paper Order Event';
  return source;
}

async function loadDiagnosticRows() {
  if (Array.isArray(logsDataCache.diagnosticRows)) return logsDataCache.diagnosticRows;

  const candidates = [
    'data/realtime_paper_diagnostic.jsonl',
    'data/realtime_paper_diagnostic_test.jsonl',
    'docs/data/realtime_paper_diagnostic.jsonl',
    'docs/data/realtime_paper_diagnostic_test.jsonl',
  ];

  let text = '';
  let sourcePath = '';
  for (const candidate of candidates) {
    try {
      const res = await fetch(`${candidate}?v=${Date.now()}`, { cache: 'no-store' });
      if (!res.ok) continue;
      text = await res.text();
      if (text && text.trim()) {
        sourcePath = candidate;
        break;
      }
    } catch (err) {
      // Continue to next candidate path.
    }
  }

  if (!text || !text.trim()) {
    logsDataCache.diagnosticRows = [];
    logsDataCache.diagnosticPath = '';
    return [];
  }

  const rows = [];
  const lines = text.split(/\r?\n/).filter(line => line.trim());
  for (const line of lines) {
    try {
      const obj = JSON.parse(line);
      const symbol = String(obj.symbol || '');
      const detail = String(obj.detail || '');
      const decision = String(obj.decision || '');
      const status = String(obj.status || '');
      const eventTime = obj.event_time || obj.pass_started_at || obj.latest_bar_ts || null;
      rows.push({
        timestamp: eventTime,
        sortMs: toEpochMs(eventTime),
        symbol,
        source: 'diagnostic',
        event: decision || 'event',
        status: status || '-',
        detail,
        raw: obj,
      });
    } catch (err) {
      // Skip malformed lines.
    }
  }

  logsDataCache.diagnosticRows = rows;
  logsDataCache.diagnosticPath = sourcePath;
  return rows;
}

function querySummaryLogsFromDb(db) {
  const out = [];
  if (!db) return out;
  try {
    const stmt = db.prepare(`
      SELECT symbol, metrics, notes
      FROM paper_trading_results
      WHERE notes LIKE '%realtime alpaca%'
      ORDER BY id DESC
    `);
    while (stmt.step()) {
      const row = stmt.getAsObject();
      let metrics = {};
      try {
        metrics = JSON.parse(String(row.metrics || '{}'));
      } catch (err) {
        metrics = {};
      }
      const ts = metrics.timestamp || null;
      out.push({
        timestamp: ts,
        sortMs: toEpochMs(ts),
        symbol: String(row.symbol || metrics.symbol || ''),
        source: 'summary',
        event: String(metrics.status || 'status'),
        status: String(metrics.status || '-'),
        detail: String(metrics.detail || row.notes || ''),
        raw: metrics,
      });
    }
    stmt.free();
  } catch (err) {
    console.error('Error querying paper_trading_results logs:', err);
  }
  return out;
}

function queryFillLogsFromDb(db) {
  const out = [];
  if (!db) return out;
  try {
    // Query paper fills
    const paperStmt = db.prepare(`
      SELECT symbol, side, qty, price, transaction_time, order_id
      FROM paper_fill_events
      ORDER BY datetime(transaction_time) DESC
    `);
    while (paperStmt.step()) {
      const row = paperStmt.getAsObject();
      const ts = row.transaction_time || null;
      const side = String(row.side || '').toLowerCase();
      const qty = Number(row.qty);
      const price = Number(row.price);
      const detailParts = [
        side ? `side=${side}` : '',
        Number.isFinite(qty) ? `qty=${qty}` : '',
        Number.isFinite(price) ? `price=${price}` : '',
        row.order_id ? `order_id=${row.order_id}` : '',
      ].filter(Boolean);
      out.push({
        timestamp: ts,
        sortMs: toEpochMs(ts),
        symbol: String(row.symbol || ''),
        source: 'fills',
        mode: 'paper',
        event: 'fill',
        status: side || '-',
        detail: detailParts.join(' • '),
        raw: row,
      });
    }
    paperStmt.free();
    
    // Query live fills if table exists
    try {
      const tableExists = db.exec("SELECT name FROM sqlite_master WHERE type='table' AND name='live_fill_events'").length > 0;
      if (tableExists) {
        const liveStmt = db.prepare(`
          SELECT symbol, side, qty, price, transaction_time, order_id
          FROM live_fill_events
          ORDER BY datetime(transaction_time) DESC
        `);
        while (liveStmt.step()) {
          const row = liveStmt.getAsObject();
          const ts = row.transaction_time || null;
          const side = String(row.side || '').toLowerCase();
          const qty = Number(row.qty);
          const price = Number(row.price);
          const detailParts = [
            side ? `side=${side}` : '',
            Number.isFinite(qty) ? `qty=${qty}` : '',
            Number.isFinite(price) ? `price=${price}` : '',
            row.order_id ? `order_id=${row.order_id}` : '',
          ].filter(Boolean);
          out.push({
            timestamp: ts,
            sortMs: toEpochMs(ts),
            symbol: String(row.symbol || ''),
            source: 'fills',
            mode: 'live',
            event: 'fill',
            status: side || '-',
            detail: detailParts.join(' • '),
            raw: row,
          });
        }
        liveStmt.free();
      }
    } catch (err) {
      // live_fill_events table may not exist, silently continue
    }
    
    // Sort combined results by timestamp descending
    out.sort((a, b) => (b.sortMs || 0) - (a.sortMs || 0));
    
  } catch (err) {
    console.error('Error querying fill events logs:', err);
  }
  return out;
}

function queryOrderLogsFromDb(db) {
  const out = [];
  if (!db) return out;
  try {
    // Query paper orders
    const paperStmt = db.prepare(`
      SELECT symbol, status, event_type, event_time, order_id, qty, notional, filled_qty, submitted_at
      FROM paper_order_events
      ORDER BY datetime(event_time) DESC
    `);
    while (paperStmt.step()) {
      const row = paperStmt.getAsObject();
      const ts = row.event_time || null;
      const status = String(row.status || '-');
      const eventType = String(row.event_type || 'order_event');
      const orderId = String(row.order_id || '').trim();
      
      // Build detail string with order quantity/notional information
      const detailParts = [];
      if (orderId) detailParts.push(`order_id=${orderId}`);
      if (row.qty) detailParts.push(`qty=${Number(row.qty).toFixed(4)}`);
      if (row.notional) detailParts.push(`notional=$${Number(row.notional).toFixed(2)}`);
      if (row.filled_qty && Number(row.filled_qty) !== Number(row.qty || 0)) {
        detailParts.push(`filled=${Number(row.filled_qty).toFixed(4)}`);
      }
      
      out.push({
        timestamp: ts,
        sortMs: toEpochMs(ts),
        symbol: String(row.symbol || ''),
        source: 'orders',
        mode: 'paper',
        event: eventType,
        status,
        detail: detailParts.length > 0 ? detailParts.join(' • ') : '',
        raw: row,
      });
    }
    paperStmt.free();
    
    // Query live orders if table exists
    try {
      const tableExists = db.exec("SELECT name FROM sqlite_master WHERE type='table' AND name='live_order_events'").length > 0;
      if (tableExists) {
        const liveStmt = db.prepare(`
          SELECT symbol, status, event_type, event_time, order_id, qty, notional, filled_qty, submitted_at
          FROM live_order_events
          ORDER BY datetime(event_time) DESC
        `);
        while (liveStmt.step()) {
          const row = liveStmt.getAsObject();
          const ts = row.event_time || null;
          const status = String(row.status || '-');
          const eventType = String(row.event_type || 'order_event');
          const orderId = String(row.order_id || '').trim();
          
          // Build detail string with order quantity/notional information
          const detailParts = [];
          if (orderId) detailParts.push(`order_id=${orderId}`);
          if (row.qty) detailParts.push(`qty=${Number(row.qty).toFixed(4)}`);
          if (row.notional) detailParts.push(`notional=$${Number(row.notional).toFixed(2)}`);
          if (row.filled_qty && Number(row.filled_qty) !== Number(row.qty || 0)) {
            detailParts.push(`filled=${Number(row.filled_qty).toFixed(4)}`);
          }
          
          out.push({
            timestamp: ts,
            sortMs: toEpochMs(ts),
            symbol: String(row.symbol || ''),
            source: 'orders',
            mode: 'live',
            event: eventType,
            status,
            detail: detailParts.length > 0 ? detailParts.join(' • ') : '',
            raw: row,
          });
        }
        liveStmt.free();
      }
    } catch (err) {
      // live_order_events table may not exist, silently continue
    }
    
    // Sort combined results by timestamp descending
    out.sort((a, b) => (b.sortMs || 0) - (a.sortMs || 0));
    
  } catch (err) {
    console.error('Error querying order events logs:', err);
  }
  return out;
}

function queryRunHistoryFromDb(db) {
  const out = [];
  if (!db) return out;
  // Table may not exist in older DB snapshots
  const tableExists = db.exec("SELECT name FROM sqlite_master WHERE type='table' AND name='realtime_paper_log'").length > 0;
  if (!tableExists) return out;
  const deriveLogEvent = (status, detail) => {
    const text = String(detail || '');
    const failed = text.match(/^failed\s+([a-z0-9_]+):/i);
    if (failed && failed[1]) return failed[1].toLowerCase();
    const latest = text.match(/^latest bar qualifies as an?\s+(.+?)$/i);
    if (latest && latest[1]) return latest[1].toLowerCase().replace(/\s+/g, '_');
    return String(status || 'run');
  };
  try {
    const stmt = db.prepare(`
      SELECT id, symbol, version, status, detail, equity, logged_at
      FROM realtime_paper_log
      ORDER BY id DESC
    `);
    while (stmt.step()) {
      const row = stmt.getAsObject();
      const ts = row.logged_at || null;
      out.push({
        timestamp: ts,
        sortMs: toEpochMs(ts),
        symbol: String(row.symbol || ''),
        source: 'runhistory',
        event: deriveLogEvent(row.status, row.detail),
        status: String(row.status || '-'),
        detail: String(row.detail || ''),
        raw: row,
      });
    }
    stmt.free();
  } catch (err) {
    console.error('Error querying realtime_paper_log:', err);
  }
  return out;
}

function queryNearMissRowsFromDb(db) {
  const out = [];
  if (!db) return out;
  const tableExists = db.exec("SELECT name FROM sqlite_master WHERE type='table' AND name='realtime_paper_log'").length > 0;
  if (!tableExists) return out;
  const deriveLogEvent = (status, detail) => {
    const text = String(detail || '');
    const failed = text.match(/^failed\s+([a-z0-9_]+):/i);
    if (failed && failed[1]) return failed[1].toLowerCase();
    return String(status || 'near_miss');
  };
  try {
    const stmt = db.prepare(`
      SELECT id, symbol, version, status, detail, equity, logged_at
      FROM realtime_paper_log
      WHERE LOWER(status) IN ('near_miss', 'holding_near_exit')
      ORDER BY id DESC
    `);
    while (stmt.step()) {
      const row = stmt.getAsObject();
      const ts = row.logged_at || null;
      out.push({
        timestamp: ts,
        sortMs: toEpochMs(ts),
        symbol: String(row.symbol || ''),
        source: 'nearmiss',
        event: deriveLogEvent(row.status, row.detail),
        status: String(row.status || '-'),
        detail: String(row.detail || ''),
        raw: row,
      });
    }
    stmt.free();
  } catch (err) {
    console.error('Error querying realtime_paper_log near misses:', err);
  }
  return out;
}

async function getLogRowsBySource(source) {
  if (source === 'diagnostic') return loadDiagnosticRows();
  const db = window._SQL_DB;
  if (!db) return [];
  if (source === 'nearmiss') return queryNearMissRowsFromDb(db);
  if (source === 'runhistory') return queryRunHistoryFromDb(db);
  if (source === 'summary') return querySummaryLogsFromDb(db);
  if (source === 'fills') return queryFillLogsFromDb(db);
  if (source === 'orders') return queryOrderLogsFromDb(db);
  return [];
}

function formatLogTimestamp(value) {
  if (!value) return '-';
  const date = new Date(String(value).replace(' ', 'T'));
  if (!Number.isFinite(date.getTime())) return String(value);
  return date.toLocaleString('en-US', {
    year: '2-digit',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

async function renderLogsPanel() {
  const sourceEl = document.getElementById('logSourceSelect');
  const scopeEl = document.getElementById('logSymbolScope');
  const searchEl = document.getElementById('logSearchInput');
  const wrap = document.getElementById('logsTableWrap');
  const countEl = document.getElementById('logsCount');
  const metaEl = document.getElementById('logsMeta');
  if (!sourceEl || !scopeEl || !searchEl || !wrap || !countEl || !metaEl) return;

  const source = sourceEl.value || 'diagnostic';
  const scope = scopeEl.value || 'active';
  const query = String(searchEl.value || '').trim().toLowerCase();
  const renderSeq = ++logsRenderSeq;

  wrap.innerHTML = '<div class="empty">Loading logs...</div>';

  let rows = await getLogRowsBySource(source);
  if (renderSeq !== logsRenderSeq) return;

// Also include __scheduler__ rows when scopeEl is 'all'
  if (scope === 'active' && activeSym) {
    const symbolKeys = getActiveSymbolKeys();
    rows = rows.filter(row => row.symbol === '__scheduler__' ? false : symbolKeys.has(getNormalizedSymbolKey(row.symbol || '')));
  }

  if (query) {
    rows = rows.filter(row => {
      const blob = `${row.timestamp || ''} ${row.symbol || ''} ${row.event || ''} ${row.status || ''} ${row.detail || ''}`.toLowerCase();
      return blob.includes(query);
    });
  }

  rows = rows.slice().sort((a, b) => (b.sortMs || 0) - (a.sortMs || 0));

  countEl.textContent = rows.length ? `${rows.length} logs` : '';
  if (source === 'diagnostic') {
    const src = logsDataCache.diagnosticPath || 'not found';
    metaEl.textContent = `Source: ${src}`;
  } else {
    metaEl.textContent = `Source: ${decodeLogSourceLabel(source)} (from tradingcopilot.db)`;
  }

  if (!rows.length) {
    wrap.innerHTML = '<div class="empty">No logs match current filters</div>';
    return;
  }

  const total = rows.length;
  const totalPages = Math.max(1, Math.ceil(total / logsPageSize));
  if (logsPage > totalPages) logsPage = totalPages;
  const start = (logsPage - 1) * logsPageSize;
  const paged = rows.slice(start, start + logsPageSize);
  const end = start + paged.length;

  const pagCtrl = total > logsPageSize ? `<div class="pagination">
    <span class="pg-info">${start + 1}-${end} of ${total} logs</span>
    <div class="pg-btns">
      <button class="pg-btn" ${logsPage <= 1 ? 'disabled' : ''} onclick="logsPage=1;renderLogsPanel()"><<</button>
      <button class="pg-btn" ${logsPage <= 1 ? 'disabled' : ''} onclick="logsPage--;renderLogsPanel()"><</button>
      <span class="pg-info" style="padding:0 8px">Page ${logsPage} / ${totalPages}</span>
      <button class="pg-btn" ${logsPage >= totalPages ? 'disabled' : ''} onclick="logsPage++;renderLogsPanel()">></button>
      <button class="pg-btn" ${logsPage >= totalPages ? 'disabled' : ''} onclick="logsPage=${totalPages};renderLogsPanel()">>></button>
    </div>
  </div>` : '';

  wrap.innerHTML = `<table><thead><tr>
    <th scope="col">Time</th><th scope="col">Source</th><th scope="col">Symbol</th><th scope="col">Event</th><th scope="col">Status</th><th scope="col">Detail</th>
  </tr></thead><tbody>${paged.map(row => {
    const statusText = escapeHtml(row.status || '-');
    const statusClass = String(row.status || '').toLowerCase();
    const statusTag = statusClass === 'error'
      ? `<span class="tag tag-sl">${statusText}</span>`
      : (statusClass === 'submitted' || statusClass === 'fill' || statusClass === 'buy' || statusClass === 'sell'
        ? `<span class="tag tag-tp">${statusText}</span>`
        : (statusClass === 'near_miss' || statusClass === 'holding_near_exit'
          ? `<span class="tag tag-mb">${statusText}</span>`
        : (statusClass === 'schedule_miss'
          ? `<span class="tag tag-trail">${statusText}</span>`
          : `<span class="tag tag-other">${statusText}</span>`)));
    const symbolLabel = row.symbol === '__scheduler__' ? 'Scheduler' : escapeHtml(getTickerSymbolLabel(row.symbol || '-'));
    return `<tr${statusClass === 'schedule_miss' ? ' style="opacity:0.8"' : ''}>
      <td>${escapeHtml(formatLogTimestamp(row.timestamp))}</td>
      <td>${escapeHtml(decodeLogSourceLabel(row.source || source))}</td>
      <td>${symbolLabel}</td>
      <td>${escapeHtml(row.event || '-')}</td>
      <td>${statusTag}</td>
      <td>${escapeHtml(row.detail || '-')}</td>
    </tr>`;
  }).join('')}</tbody></table>${pagCtrl}`;
}

function getAllSymbolsCumulativeEquity() {
  const db = window._SQL_DB;
  if (!db) return null;
  if (activeDataset !== 'backtest') {
    const baseline = getDatasetInitialCapital();
    return { equity: baseline, baseline };
  }
  const modeFilter = activeDataset === 'backtest' ? 'backtest' : (activeDataset === 'paper' ? 'paper' : 'live');
  const rowsBySymbolVersion = new Map();
  try {
    const stmt = db.prepare("SELECT symbol, version, equity, dollar_pnl, direction, result, entry_time, exit_time FROM trades WHERE mode = ? AND LOWER(version) IN ('v6')");
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
  if (activeDataset === 'live') return [];
  const txns = [];
  const symData = INSTRUMENTS[activeSym];
  const sameDaySimOnly = activeDataset === 'paper'
    && paperTradeSourceFilter === 'simulation'
    && simulationDataScopeFilter === 'same_day';
  const todayDateKey = sameDaySimOnly ? getUtcDateKey(0) : '';
  for (const [ver, cfg] of Object.entries(symData.versions)) {
    const rows = filterPaperRows(loaded[activeSym][ver] || []);
    let prevEquity = getInitialCapitalFromRows(rows);
    for (const r of rows) {
      const begEquity = prevEquity;
      const isLong = r.direction === 'long';
      const src = activeDataset === 'paper' ? normalizeSource(r.source) : (r.source || null);
      const includeOpen = !sameDaySimOnly || getUtcDateFromTimestamp(r.entry_time) === todayDateKey;
      const includeClose = !sameDaySimOnly || getUtcDateFromTimestamp(r.exit_time) === todayDateKey;
      if (includeOpen) {
        txns.push({ time:r.entry_time, sym:activeSym, ver, cfg, symLabel:symData.label,
          action: isLong?'BUY':'SELL', price:r.entry_price, type:'Open',
          direction:r.direction, pnl:null, result:null, begEquity, endEquity:null, source:src });
      }
      if (includeClose) {
        txns.push({ time:r.exit_time, sym:activeSym, ver, cfg, symLabel:symData.label,
          action: isLong?'SELL':'BUY', price:r.exit_price, type:'Close',
          direction:r.direction, pnl:r.dollar_pnl, result:r.result, begEquity, endEquity:r.equity, source:src });
      }
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
  // Show a source notice when in paper mode and rows are simulation-only or mixed.
  const isPaperMode = activeDataset === 'paper';
  const simCount = isPaperMode ? txns.filter(t => t.source === 'simulation').length : 0;
  const realtimeCount = isPaperMode ? txns.filter(t => t.source === 'realtime').length : 0;
  const hasSimOnly = isPaperMode && simCount > 0 && realtimeCount === 0;
  const hasMixed = isPaperMode && simCount > 0 && realtimeCount > 0;
  const sourceNotice = hasSimOnly
    ? `<div style="margin-bottom:10px;padding:8px 12px;border-radius:6px;background:#d2950022;border:1px solid #d29500;color:#d29500;font-size:12px;font-weight:500;">
        ⚠ Paper trading data is backtest simulation — no live Alpaca broker orders have been placed for this symbol.
       </div>`
    : hasMixed
    ? `<div style="margin-bottom:10px;padding:8px 12px;border-radius:6px;background:#58a6ff22;border:1px solid #58a6ff;color:#58a6ff;font-size:12px;font-weight:500;">
        ℹ Mix of simulation and live broker trades. Simulation rows are marked <span style="font-variant:small-caps">sim</span>.
       </div>`
    : '';
  wrap.innerHTML = `${sourceNotice}<table><thead><tr>
    <th scope="col">Date / Time</th><th scope="col">Version</th><th scope="col">Action</th><th scope="col">Type</th><th scope="col">Direction</th><th scope="col">Price</th><th scope="col">P&L</th><th scope="col">Beg. Bal</th><th scope="col">End Bal</th><th scope="col">Result</th>
  </tr></thead><tbody>${paged.map(t => {
    const fmtP = p => isNaN(p)?'-' : p<100?'$'+p.toFixed(4):'$'+p.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    const actionTag = t.action==='BUY'
      ? `<span class="tag tag-buy">BUY</span>`
      : `<span class="tag tag-sell">SELL</span>`;
    const simBadge = (isPaperMode && t.source === 'simulation' && !hasSimOnly)
      ? `<span style="display:inline-block;margin-left:4px;font-size:10px;padding:1px 4px;border-radius:3px;background:#d2950022;color:#d29500;border:1px solid #d29500;font-variant:small-caps">sim</span>`
      : '';
    const typeTag = t.type==='Open'
      ? `<span class="tag tag-open">Open</span>${simBadge}`
      : `<span class="tag tag-close">Close</span>${simBadge}`;
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
    const rows = filterPaperRows(loaded[sym][vk] || []);
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
  const items=vkeys.map(v=>{ const r=filterPaperRows(loaded[activeSym][v]||[]); return { v, m: r.length ? calcMetrics(r) : null, cfg:vers[v] }; });
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

  if (activeDataset !== 'backtest') {
    if (endEl) {
      endEl.textContent = '-';
      endEl.className = 'bal-value neutral';
    }
    fmtBal(startCapital, totalEl, startCapital);
    if (totalAllEl) fmtBal(startCapital, totalAllEl, startCapital);
    if (totalAllSymbolsEl) fmtBal(startCapital, totalAllSymbolsEl, startCapital);
    return;
  }

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
  const rawRows=activeTab==='all'?Object.values(loaded[activeSym]).flat():(loaded[activeSym][activeTab]||[]);
  const rows=filterPaperRows(rawRows);
  updateDatasetSwitcher();
  updatePaperSourceBar();
  renderTransactionTicker();
  updateBalanceBar(activeTab === 'all' ? null : rows);
  renderCards(rows);
  renderEquityChart(rows);
  renderOutcomeChart(rows);
  renderDirectionChart(rows);
  renderMonthlyChart(rows);
  const has1D=activeTab!=='all'
    ?(vers[activeTab]?.hasYear&&rows.length>0)
    :Object.keys(vers).some(v=>vers[v].hasYear&&filterPaperRows(loaded[activeSym][v]||[]).length);
  const yearSection=document.getElementById('yearSection');
  if (has1D) { yearSection.style.display=''; renderYearChart(); }
  else        { yearSection.style.display='none'; destroyChart('year'); }
  renderTradeTable(rows);
  renderComparisonTable();
  renderTransactionsTable();
  renderLogsPanel();
  renderPriceChart();
}

function updatePaperSourceBar() {
  const bar = document.getElementById('paperSourceBar');
  const scopeBar = document.getElementById('simulationScopeBar');
  if (!bar) return;
  const show = activeDataset === 'paper';
  bar.style.display = show ? 'flex' : 'none';
  bar.querySelectorAll('.paper-src-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.src === paperTradeSourceFilter);
  });
  if (scopeBar) {
    const showScope = show && paperTradeSourceFilter === 'simulation';
    scopeBar.style.display = showScope ? 'flex' : 'none';
    scopeBar.querySelectorAll('.sim-scope-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.simScope === simulationDataScopeFilter);
    });
  }
}

function updateAutoRefreshStatus({ enabled = false, timestamp = null, intervalSeconds = 0, failed = false } = {}) {
  const statusEl = document.getElementById('autoRefreshStatus');
  const statusTextEl = document.getElementById('autoRefreshStatusText');
  const statusDotEl = document.getElementById('autoRefreshStatusDot');
  if (!statusEl) return;
  const setState = (state, text) => {
    if (statusTextEl) statusTextEl.textContent = text;
    else statusEl.textContent = text;
    if (statusDotEl) statusDotEl.dataset.state = state;
  };
  if (!enabled) {
    setState('off', 'Last auto refresh: Off');
    return;
  }
  if (failed) {
    setState('failed', 'Last auto refresh: Failed');
    return;
  }
  if (!timestamp || !Number.isFinite(timestamp.getTime())) {
    setState('enabled', `Last auto refresh: Enabled (${intervalSeconds}s)`);
    return;
  }
  const timeStr = timestamp.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  setState('success', `Last auto refresh: ${timeStr}`);
}

async function refreshDashboardData(reason = 'manual') {
  if (dashboardRefreshInFlight) return;
  dashboardRefreshInFlight = true;
  const reloadBtn = document.getElementById('reloadDashboardBtn');
  const autoSelect = document.getElementById('autoRefreshSelect');
  const previousLabel = reloadBtn ? reloadBtn.textContent : '';
  if (reloadBtn) {
    reloadBtn.disabled = true;
    reloadBtn.textContent = reason === 'auto' ? 'Auto Refreshing...' : 'Refreshing...';
  }
  if (autoSelect) autoSelect.disabled = true;

  try {
    const currentSelect = document.getElementById('symbolSelect');
    pendingDatasetSymbol = (currentSelect && currentSelect.value) || activeSym || '';
    Object.keys(chartDataCache).forEach(key => { delete chartDataCache[key]; });
    await loadSymbolsAndInit();
    if (reason === 'auto') {
      const autoValue = Number(document.getElementById('autoRefreshSelect')?.value || 0);
      updateAutoRefreshStatus({ enabled: autoValue > 0, timestamp: new Date(), intervalSeconds: autoValue });
    }
  } catch (err) {
    console.error('Dashboard refresh failed:', err);
    if (reason === 'auto') {
      const autoValue = Number(document.getElementById('autoRefreshSelect')?.value || 0);
      updateAutoRefreshStatus({ enabled: autoValue > 0, failed: true, intervalSeconds: autoValue });
    }
  } finally {
    if (reloadBtn) {
      reloadBtn.disabled = false;
      reloadBtn.textContent = previousLabel || 'Reload Data';
    }
    if (autoSelect) autoSelect.disabled = false;
    dashboardRefreshInFlight = false;
  }
}

function setDashboardAutoRefresh(seconds) {
  if (dashboardAutoRefreshTimer) {
    clearInterval(dashboardAutoRefreshTimer);
    dashboardAutoRefreshTimer = null;
  }
  if (!Number.isFinite(seconds) || seconds <= 0) {
    updateAutoRefreshStatus({ enabled: false });
    return;
  }
  updateAutoRefreshStatus({ enabled: true, intervalSeconds: seconds });
  dashboardAutoRefreshTimer = setInterval(() => {
    refreshDashboardData('auto');
  }, seconds * 1000);
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
function handleSymbolSelect(newSym, dbInstance) {
  console.log('[DEBUG] handleSymbolSelect called with:', newSym, dbInstance);
  console.log('[DEBUG] activeSym:', activeSym, 'loaded:', loaded && loaded[activeSym]);
  const hasAnyData = Object.values(loaded[activeSym] || {}).some(v => v && v.length > 0);
  console.log('[DEBUG] hasAnyData:', hasAnyData, 'for symbol:', activeSym);
  const noDataNotice = document.getElementById('noDataNotice');
  if (noDataNotice) noDataNotice.style.display = hasAnyData ? 'none' : '';
  if (hasAnyData) {
    console.log('[DEBUG] showDashboardData called');
    showDashboardData();
  } else {
    console.log('[DEBUG] hideDashboardData called');
    hideDashboardData();
    if (noDataNotice) noDataNotice.style.display = '';
  }
  buildTabs();
  render();
  updateLastUpdated();
  renderTransactionTicker();
  updateModeButtonStates();
}
    updateModeButtonStates();
    const removeBtn = document.getElementById('removeSymbolBtn');
    if (removeBtn) { removeBtn.disabled = true; removeBtn.style.opacity = '0.4'; }
    renderTransactionTicker();
    return;
  }
  if (newSym === activeSym) return;
  activeSym = newSym;
  resetTransactionFilters();
  activeTab = 'all'; tradeTablePage = 1; txPage = 1;
  logsPage = 1;
  const removeBtn = document.getElementById('removeSymbolBtn');
  if (removeBtn) { removeBtn.disabled = false; removeBtn.style.opacity = '1'; }
  if (!loaded[activeSym]) loaded[activeSym] = {};
  const vers = INSTRUMENTS[activeSym]?.versions;
  if (!vers) {
    hideDashboardData();
    updateModeButtonStates();
    renderTransactionTicker();
    return;
  }
  // Use dbInstance if provided, else window._SQL_DB
  const db = dbInstance || window._SQL_DB;
  console.log('[DEBUG] DB instance in handleSymbolSelect:', db);
  if (!db) {
    console.error('No SQL DB instance available');
    renderTransactionTicker();
    return;
  }
    // Prefer trade-level rows for every dataset. Symbol formats vary across
    // sources (e.g. BTC/USD vs BTC_USD), so query common aliases.
    const symbolAliases = getSymbolAliases(activeSym);
    const normalizedSymbol = getNormalizedSymbolKey(activeSym);
    const modeFilter = activeDataset === 'backtest' ? 'backtest' : (activeDataset === 'paper' ? 'paper' : 'live');
    const requireBrokerRows = activeDataset === 'live' || (activeDataset === 'paper' && paperTradeSourceFilter === 'realtime');
    const linkTable = modeFilter === 'live' ? 'live_order_trade_links' : 'paper_order_trade_links';
    const hasLinkTable = !requireBrokerRows || sqliteTableExists(db, linkTable);
    let rows = [];
    try {
      if (!hasLinkTable) {
        rows = [];
      } else {
        const sourceClause = activeDataset === 'paper' && paperTradeSourceFilter === 'realtime'
          ? "AND COALESCE(LOWER(source), '') = 'realtime'"
          : '';
        const brokerClause = requireBrokerRows
          ? `AND EXISTS (SELECT 1 FROM ${linkTable} l WHERE l.trade_id = trades.id)`
          : '';

        const stmt = db.prepare(
          `SELECT * FROM trades
           WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
             AND mode = ?
             ${sourceClause}
             ${brokerClause}
           ORDER BY entry_time`
        );
        stmt.bind([normalizedSymbol, modeFilter]);
        while (stmt.step()) {
          rows.push(stmt.getAsObject());
        }
        stmt.free();
      }
      if (requireBrokerRows) {
        rows = rows.filter(r => String(r.source || '').toLowerCase() === 'realtime');
      }
    } catch (e) {
      console.error('Error querying trades table:', e);
    }
    console.log('[DEBUG] trade rows fetched for', activeSym, 'aliases:', symbolAliases, 'normalized:', normalizedSymbol, 'brokerOnly:', requireBrokerRows, 'count:', rows.length, rows);

    // Summary fallback: use result summaries for versions missing trade rows.
    let summaryRows = [];
    if (activeDataset === 'backtest' || activeDataset === 'paper') {
      try {
        const summaryTable = activeDataset === 'backtest' ? 'backtest_results' : 'paper_trading_results';
        const summaryNotesFilter = activeDataset === 'backtest'
          ? "AND notes LIKE '%backtest summary%'"
          : "AND notes LIKE '%paper trading summary%'";
        const stmt = db.prepare(
          `SELECT metrics, notes, timestamp FROM ${summaryTable}
           WHERE REPLACE(REPLACE(REPLACE(REPLACE(UPPER(symbol), '/', ''), '_', ''), '-', ''), ' ', '') = ?
             ${summaryNotesFilter}
           ORDER BY timestamp`
        );
        stmt.bind([normalizedSymbol]);
        while (stmt.step()) {
          summaryRows.push(stmt.getAsObject());
        }
        stmt.free();
      } catch (e) {
        console.error('Error querying summary table:', e);
      }
      console.log('[DEBUG] summary rows fetched for', activeSym, 'dataset:', activeDataset, 'count:', summaryRows.length);
    }

    const buildSummaryRows = (metrics, notes, timestamp, version) => {
      const startTime = metrics.first_trade_date || timestamp || null;
      const endTime = metrics.last_trade_date || metrics.first_trade_date || timestamp || null;
      const beginEq = Number(metrics.beginning_equity || getDatasetInitialCapital());
      const finalEq = Number(metrics.current_equity || metrics.final_equity || beginEq);
      const netPnl = Number(metrics.total_pnl || (finalEq - beginEq));
      return [
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
          _notes: notes || '',
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
          _notes: notes || '',
        },
      ];
    };

    const summaryByVersion = {};
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
      summaryByVersion[version] = buildSummaryRows(metrics, r.notes, r.timestamp, version);
    });

    // Group by version and store in loaded cache
    const byVersion = {};
    if (rows.length === 0 && (activeDataset === 'backtest' || activeDataset === 'paper')) {
      Object.assign(byVersion, summaryByVersion);
    } else {
      const byVersionAllRows = {};
      rows.forEach(r => {
        const versionKey = String(r.version || 'v1').toLowerCase();
        if (!byVersionAllRows[versionKey]) byVersionAllRows[versionKey] = [];
        byVersionAllRows[versionKey].push({
          ...r,
          version: versionKey,
        });
      });

      Object.entries(byVersionAllRows).forEach(([versionKey, versionRows]) => {
        // Preserve all rows for the selected dataset; source filtering is applied
        // consistently by filterPaperRows() based on the active source toggle.
        byVersion[versionKey] = versionRows;
      });

      if (activeDataset === 'backtest' || activeDataset === 'paper') {
        // Fill per-version gaps with summaries (for legitimate zero-trade versions).
        Object.keys(vers).forEach(versionKey => {
          if ((!byVersion[versionKey] || byVersion[versionKey].length === 0) && summaryByVersion[versionKey]) {
            byVersion[versionKey] = summaryByVersion[versionKey];
          }
        });
      }
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
    renderTransactionTicker();
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

for (const version of VERSION_KEYS) {
  document.getElementById(`${version}DatasetSelect`)?.addEventListener('change', event => {
    handleBacktestVariantChange(version, event.target.value);
  });
}

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

  const accountBtn = document.getElementById('openAccountInfoBtn');
  accountBtn?.addEventListener('click', openAccountInfoModal);

  const closeAccountBtn = document.getElementById('closeAccountInfoBtn');
  closeAccountBtn?.addEventListener('click', closeAccountInfoModal);

  const accountModal = document.getElementById('accountInfoModal');
  accountModal?.addEventListener('click', event => {
    if (event.target === accountModal) closeAccountInfoModal();
  });

  const dailyTransactionsBtn = document.getElementById('openDailyTransactionsBtn');
  dailyTransactionsBtn?.addEventListener('click', openDailyTransactionsModal);

  const dailyValidationBadge = document.getElementById('dailyValidationBadge');
  dailyValidationBadge?.addEventListener('click', openDailyTransactionsModal);
  dailyValidationBadge?.addEventListener('mouseenter', showDailyValidationPopover);
  dailyValidationBadge?.addEventListener('focus', showDailyValidationPopover);
  dailyValidationBadge?.addEventListener('mouseleave', () => queueHideDailyValidationPopover());
  dailyValidationBadge?.addEventListener('blur', () => queueHideDailyValidationPopover());

  const dailyValidationPopover = document.getElementById('dailyValidationPopover');
  dailyValidationPopover?.addEventListener('mouseenter', () => clearDailyValidationPopoverHideTimer());
  dailyValidationPopover?.addEventListener('mouseleave', () => queueHideDailyValidationPopover());
  dailyValidationPopover?.addEventListener('click', async event => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.id !== 'copyDailyValidationBtn') return;
    event.preventDefault();
    const ok = await copyDailyValidationSummary();
    setDailyValidationCopyStatus(ok ? 'Copied' : 'Copy failed', !ok);
  });

  document.addEventListener('scroll', hideDailyValidationPopover, true);
  document.addEventListener('resize', hideDailyValidationPopover);
  document.addEventListener('click', event => {
    const pop = document.getElementById('dailyValidationPopover');
    if (!pop || !pop.classList.contains('open')) return;
    if (event.target === pop || pop.contains(event.target)) return;
    if (dailyValidationBadge && (event.target === dailyValidationBadge || dailyValidationBadge.contains(event.target))) return;
    hideDailyValidationPopover();
  });

  const closeDailyTransactionsBtn = document.getElementById('closeDailyTransactionsBtn');
  closeDailyTransactionsBtn?.addEventListener('click', closeDailyTransactionsModal);

  const tradeGapBtn = document.getElementById('openTradeGapBtn');
  tradeGapBtn?.addEventListener('click', openTradeGapModal);

  const openGuidelineAuditBtn = document.getElementById('openGuidelineAuditBtn');
  openGuidelineAuditBtn?.addEventListener('click', openGuidelineAuditModal);

  const closeGuidelineAuditBtn = document.getElementById('closeGuidelineAuditBtn');
  closeGuidelineAuditBtn?.addEventListener('click', closeGuidelineAuditModal);

  const guidelineAuditModal = document.getElementById('guidelineAuditModal');
  guidelineAuditModal?.addEventListener('click', event => {
    if (event.target === guidelineAuditModal) closeGuidelineAuditModal();
  });

  // Tab switching inside the guideline audit modal
  document.getElementById('guidelineTabStatus')?.addEventListener('click', () => switchGuidelineAuditTab('status'));
  document.getElementById('guidelineTabCompare')?.addEventListener('click', () => switchGuidelineAuditTab('compare'));

  const guidelineAuditContent = document.getElementById('guidelineAuditContent');
  guidelineAuditContent?.addEventListener('click', event => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const btn = target.closest('.guideline-rerun-btn');
    if (!btn) return;
    const symbol = String(btn.getAttribute('data-symbol') || '').trim();
    const version = String(btn.getAttribute('data-version') || '').trim().toLowerCase();
    if (!symbol || !version) return;
    openWorkflowIssue('backtest', symbol, version);
  });

  const closeTradeGapBtn = document.getElementById('closeTradeGapBtn');
  closeTradeGapBtn?.addEventListener('click', closeTradeGapModal);

  const tradeGapModal = document.getElementById('tradeGapModal');
  tradeGapModal?.addEventListener('click', event => {
    if (event.target === tradeGapModal) closeTradeGapModal();
  });

  const openLiveSymbolControlBtn = document.getElementById('openLiveSymbolControlBtn');
  openLiveSymbolControlBtn?.addEventListener('click', openLiveSymbolControlModal);

  const closeLiveSymbolControlBtn = document.getElementById('closeLiveSymbolControlBtn');
  closeLiveSymbolControlBtn?.addEventListener('click', closeLiveSymbolControlModal);

  const liveSymbolControlModal = document.getElementById('liveSymbolControlModal');
  liveSymbolControlModal?.addEventListener('click', event => {
    if (event.target === liveSymbolControlModal) closeLiveSymbolControlModal();
  });

  const liveSymbolControlContent = document.getElementById('liveSymbolControlContent');
  liveSymbolControlContent?.addEventListener('click', event => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const btn = target.closest('.live-toggle-btn');
    if (!btn) return;
    const symbol = String(btn.getAttribute('data-symbol') || '').trim();
    const targetEnabled = String(btn.getAttribute('data-target-enabled') || '0') === '1';
    const currentEnabled = String(btn.getAttribute('data-current-enabled') || '0') === '1';
    if (!symbol) return;
    const url = buildLiveToggleIssueUrl(symbol, targetEnabled, currentEnabled);
    window.open(url, '_blank');
  });

  const refreshDailyTransactionsBtn = document.getElementById('refreshDailyTransactionsBtn');
  refreshDailyTransactionsBtn?.addEventListener('click', () => {
    updateDailyTransactionsDateControls();
    renderDailyTransactionsModal();
  });

  const dailyTransactionsTodayBtn = document.getElementById('dailyTransactionsTodayBtn');
  dailyTransactionsTodayBtn?.addEventListener('click', () => {
    dailyTransactionsDateOffsetDays = 0;
    updateDailyTransactionsDateControls();
    renderDailyTransactionsModal();
  });

  const dailyTransactionsYesterdayBtn = document.getElementById('dailyTransactionsYesterdayBtn');
  dailyTransactionsYesterdayBtn?.addEventListener('click', () => {
    dailyTransactionsDateOffsetDays = -1;
    updateDailyTransactionsDateControls();
    renderDailyTransactionsModal();
  });

  const dailyTransactionsModal = document.getElementById('dailyTransactionsModal');
  dailyTransactionsModal?.addEventListener('click', event => {
    if (event.target === dailyTransactionsModal) closeDailyTransactionsModal();
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeAccountInfoModal();
      closeDailyTransactionsModal();
      closeTradeGapModal();
      closeGuidelineAuditModal();
      closeLiveSymbolControlModal();
    }
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
  document.getElementById('paperSourceBar')?.addEventListener('click', e => {
    const btn = e.target.closest('.paper-src-btn');
    if (!btn) return;
    paperTradeSourceFilter = btn.dataset.src || 'all';
    tradeTablePage = 1;
    updatePaperSourceBar();
    render();
  });
  document.getElementById('simulationScopeBar')?.addEventListener('click', e => {
    const btn = e.target.closest('.sim-scope-btn');
    if (!btn) return;
    simulationDataScopeFilter = btn.dataset.simScope === 'same_day' ? 'same_day' : 'historical';
    tradeTablePage = 1;
    txPage = 1;
    updatePaperSourceBar();
    render();
    updateWorkflowStatus(
      `Simulation scope set to ${simulationDataScopeFilter === 'same_day' ? 'Same Day' : 'Historical'}.`,
      '#58a6ff'
    );
  });
  const logsRerender = () => { logsPage = 1; renderLogsPanel(); };
  document.getElementById('logSourceSelect')?.addEventListener('change', () => {
    logsDataCache.diagnosticRows = null;
    logsDataCache.diagnosticPath = null;
    logsRerender();
  });
  document.getElementById('logSymbolScope')?.addEventListener('change', logsRerender);
  document.getElementById('logSearchInput')?.addEventListener('input', logsRerender);
  document.getElementById('logPageSizeSelect')?.addEventListener('change', e => {
    logsPageSize = parseInt(e.target.value, 10);
    logsPage = 1;
    renderLogsPanel();
  });
  document.getElementById('transactionTickerTrack')?.addEventListener('click', event => {
    const button = event.target.closest('.ticker-item[data-symbol]');
    if (!button) return;
    const rawSymbol = button.dataset.symbol || '';
    const normalized = getNormalizedSymbolKey(rawSymbol);
    const select = document.getElementById('symbolSelect');
    const db = window._SQL_DB;
    if (!normalized || !select || !db) return;
    const matchedOption = [...select.options].find(option => getNormalizedSymbolKey(option.value) === normalized);
    const symbol = matchedOption?.value || rawSymbol;
    select.value = symbol;
    handleSymbolSelect(symbol, db);
    setTimeout(() => button.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' }), 100);
  });

  const reloadDashboardBtn = document.getElementById('reloadDashboardBtn');
  reloadDashboardBtn?.addEventListener('click', () => {
    logsDataCache.diagnosticRows = null;
    logsDataCache.diagnosticPath = null;
    refreshDashboardData('manual');
  });

  const autoRefreshSelect = document.getElementById('autoRefreshSelect');
  autoRefreshSelect?.addEventListener('change', event => {
    const value = Number(event.target.value);
    setDashboardAutoRefresh(value);
  });

  window.addEventListener('beforeunload', () => {
    if (dashboardAutoRefreshTimer) {
      clearInterval(dashboardAutoRefreshTimer);
      dashboardAutoRefreshTimer = null;
    }
  });
}

bindStaticControlHandlers();


