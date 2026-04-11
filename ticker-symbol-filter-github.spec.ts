import { test, expect } from '@playwright/test';

test('ticker updates for selected symbol on GitHub Pages', async ({ page }) => {
  // Log browser console messages
  page.on('console', msg => {
    console.log(`[browser][${msg.type()}] ${msg.text()}`);
  });
  // Replace with your actual GitHub Pages URL
  const githubPagesUrl = 'https://rcaldwell67.github.io/pinescripts/docs/index.html';
  await page.goto(githubPagesUrl);

  // Wait for the symbol dropdown to be visible
  const symbolSelect = page.locator('#symbolSelect');
  await expect(symbolSelect).toBeVisible();

  // Select a symbol (e.g., BTCUSD)
  await symbolSelect.selectOption('BTCUSD');

  // Wait for the ticker to update
  const tickerTrack = page.locator('#transactionTickerTrack .ticker-item');
  await expect(tickerTrack).toBeVisible();

  // Check that the ticker only shows the selected symbol
  const tickerSymbols = await page.$$eval('#transactionTickerTrack .ticker-symbol', els => els.map(e => e.textContent?.trim()));
  expect(tickerSymbols.length).toBeGreaterThan(0);
  for (const symbol of tickerSymbols) {
    expect(symbol).toBe('BTCUSD');
  }
});