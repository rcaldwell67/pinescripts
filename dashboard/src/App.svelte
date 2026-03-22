
<script>
  import { onMount } from 'svelte';
  let symbol = '';
  let loading = false;
  let error = '';
  let summary = null;

  async function runBacktest() {
    error = '';
    summary = null;
    if (!symbol) {
      error = 'Please enter a symbol.';
      return;
    }
    loading = true;
    try {
      // If running on GitHub Pages (static), load from static files
      if (window.location.protocol === 'file:' || window.location.hostname.endsWith('github.io')) {
        // Try to load all timeframes from public/data
        const timeframes = ["5m", "10m", "15m", "30m", "1h", "1d"];
        let staticSummary = {};
        for (const tf of timeframes) {
          try {
            const resp = await fetch(`data/${symbol}_${tf}_backtest.json`);
            if (!resp.ok) throw new Error('Not found');
            const result = await resp.json();
            staticSummary[tf] = result;
          } catch (e) {
            staticSummary[tf] = { error: 'No static result' };
          }
        }
        summary = staticSummary;
      } else {
        // Use API if running locally
        const res = await fetch('http://localhost:8000/api/backtest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol })
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        summary = data.summary;
      }
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
</script>



<header>
  <div>
    <h1>APM Dashboard</h1>
    <div class="subtitle">Adaptive Pullback Momentum</div>
  </div>
  <form on:submit|preventDefault={runBacktest} style="margin: 1em 0; display: flex; gap: 1em; align-items: center;">
    <input type="text" placeholder="Symbol (e.g. BTCUSD)" bind:value={symbol} />
    <button type="submit" disabled={loading}>{loading ? 'Running…' : 'Run Backtest'}</button>
  </form>
  {#if error}
    <div style="color: red;">{error}</div>
  {/if}
</header>


<main>
  {#if summary}
    <section class="panel">
      <h2>Backtest Summary</h2>
      <table>
        <thead>
          <tr>
            <th>Timeframe</th>
            <th>Trades</th>
            <th>Net Return</th>
            <th>Win Rate</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {#each Object.entries(summary) as [tf, res]}
            <tr>
              <td>{tf}</td>
              <td>{res.trades ?? '-'}</td>
              <td>{res.net_return !== undefined ? (res.net_return * 100).toFixed(2) + '%' : '-'}</td>
              <td>{res.win_rate !== undefined ? (res.win_rate * 100).toFixed(1) + '%' : '-'}</td>
              <td>{res.error ?? ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
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
