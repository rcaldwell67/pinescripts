<script>
  // Dashboard state and logic will be added in follow-up steps
  // TODO: Import and use Svelte components for each section as they are created
</script>


<header>
  <div>
    <h1>APM Dashboard</h1>
    <div class="subtitle">Adaptive Pullback Momentum</div>
  </div>
  <nav class="sym-switcher"><!-- SymbolSwitcher component --></nav>
  <nav class="mode-switcher"><!-- ModeSwitcher component --></nav>
  <section class="dataset-switcher" id="datasetSwitcher" style="display:none"><!-- DatasetSwitcher component --></section>
  <section id="balanceBar"><!-- BalanceBar component --></section>
  <span id="lastUpdated"><!-- LastUpdated --></span>
</header>

<main>
  <nav class="tabs" id="tabs"><!-- Tabs component --></nav>
  <section class="cards" id="cards"><!-- StatCards component --></section>
  <section class="panel" style="margin-bottom:16px;">
    <div class="tx-controls"><!-- Transactions controls/filters --></div>
    <div class="table-wrap" id="txTableWrap"><!-- TransactionsTable component --></div>
  </section>
  <section class="panel" id="priceChartPanel"><!-- PriceChart component --></section>
  <section class="grid-3" id="topRow">
    <div class="panel chart-wrap tall"><!-- EquityChart component --></div>
    <div class="panel chart-wrap"><!-- OutcomeChart component --></div>
  </section>
  <section class="grid-2" id="midRow">
    <div class="panel chart-wrap"><!-- DirectionChart component --></div>
    <div class="panel chart-wrap"><!-- MonthlyChart component --></div>
  </section>
  <section class="panel" id="yearSection"><!-- YearChart component --></section>
  <section class="panel"><!-- TradeLogTable component --></section>
  <section class="panel"><!-- ComparisonTable component --></section>
</main>

<main>
  <div class="tabs" id="tabs"></div>
  <div class="cards" id="cards"></div>
  <div class="panel" style="margin-bottom:16px;">
    <div class="tx-controls">
      <div style="display:flex;align-items:baseline;gap:10px;">
        <h2 style="margin-bottom:0;">All Transactions</h2>
        <span class="tx-count" id="txCount"></span>
      </div>
      <div class="tx-filters">
        <select id="txVerFilter" class="tx-select"><option value="all">All Versions</option></select>
        <select id="txTfFilter" class="tx-select"><option value="all">All Timeframes</option></select>
        <select id="txActionFilter" class="tx-select"><option value="all">All Actions</option><option value="BUY">BUY</option><option value="SELL">SELL</option></select>
        <select id="txDirFilter" class="tx-select"><option value="all">All Directions</option><option value="long">Long</option><option value="short">Short</option></select>
        <select id="txTypeFilter" class="tx-select"><option value="all">Open &amp; Close</option><option value="Open">Open Only</option><option value="Close">Close Only</option></select>
        <div class="pg-size"><label>Rows</label><select id="txPageSizeSelect" class="tx-select"><option value="10">10</option><option value="25" selected>25</option><option value="50">50</option><option value="100">100</option></select></div>
      </div>
    </div>
    <div class="table-wrap" id="txTableWrap"><div class="empty">Loading…</div></div>
  </div>
  <!-- More dashboard sections will be added here in follow-up steps -->
</main>
        <a href="https://chat.vite.dev/" target="_blank" rel="noreferrer">
          <svg class="button-icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#discord-icon"></use>
          </svg>
          Discord
        </a>
      </li>
      <li>
        <a href="https://x.com/vite_js" target="_blank" rel="noreferrer">
          <svg class="button-icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#x-icon"></use>
          </svg>
          X.com
        </a>
      </li>
      <li>
        <a href="https://bsky.app/profile/vite.dev" target="_blank" rel="noreferrer">
          <svg class="button-icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#bluesky-icon"></use>
          </svg>
          Bluesky
        </a>
      </li>
    </ul>
  </div>
</section>

<div class="ticks"></div>
<section id="spacer"></section>
