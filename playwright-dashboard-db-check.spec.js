// playwright-dashboard-db-check.spec.js
// Playwright test: checks DB load, symbol selection, and transaction rendering.
const { test, expect } = require('@playwright/test');

test('Dashboard loads tradingcopilot.db and BTC symbol transactions render', async ({ page }) => {
  const dbResponsePromise = page.waitForResponse(resp =>
    resp.url().includes('tradingcopilot.db') && resp.status() === 200,
    { timeout: 45000 }
  );

  // Go to the dashboard
  await page.goto('https://rcaldwell67.github.io/pinescripts/');

  // Wait for the symbol dropdown to be enabled (populated from db)
  const symbolSelect = page.locator('#symbolSelect');
  await expect(symbolSelect).toBeVisible();
  await expect(symbolSelect).not.toBeDisabled();

  // Options are populated asynchronously after DB + SQL.js init.
  await expect.poll(async () => {
    return await symbolSelect.locator('option').count();
  }, { timeout: 45000 }).toBeGreaterThan(1);

  // Check that tradingcopilot.db was loaded (network)
  const dbRequest = await dbResponsePromise;
  expect(dbRequest).toBeTruthy();

  // Select BTC symbol from the dropdown (supports BTC/USD and BTC_USD values).
  const optionValues = await symbolSelect.locator('option').evaluateAll(options =>
    options.map(opt => ({ value: opt.value, text: opt.textContent || '' }))
  );
  const btcOption = optionValues.find(opt => /BTC[\/_]?USD/i.test(opt.value) || /BTC[\/_]?USD/i.test(opt.text));
  expect(btcOption, `BTC symbol option not found. Values: ${JSON.stringify(optionValues)}`).toBeTruthy();
  await symbolSelect.selectOption(btcOption.value);

  // Wait for dashboard data to update.
  const cards = page.locator('#cards .card');
  await expect(cards.first()).toBeVisible();

  // Ensure transaction panel content is present (rows or empty-state message).
  const txWrap = page.locator('#txTableWrap');
  await expect(txWrap).toBeVisible();
  await expect(txWrap).not.toBeEmpty();

  // Optionally, log the card text for debugging
  const cardTexts = await cards.allTextContents();
  console.log('Card texts:', cardTexts);

  // Check for errors in the console
  const errors = [];
  page.on('pageerror', err => errors.push(err));
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });

  // Wait a bit for any errors to appear
  await page.waitForTimeout(1000);
  expect(errors).toEqual([]);
});
