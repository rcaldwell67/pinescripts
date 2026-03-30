// playwright-dashboard-db-check.spec.js
// Playwright test: Checks if tradingcopilot.db loads and BTC_USD can be selected
const { test, expect } = require('@playwright/test');

test('Dashboard loads tradingcopilot.db and BTC_USD selection works', async ({ page }) => {
  // Go to the dashboard
  await page.goto('https://rcaldwell67.github.io/pinescripts/');

  // Wait for the symbol dropdown to be enabled (populated from db)
  const symbolSelect = page.locator('#symbolSelect');
  await expect(symbolSelect).toBeVisible();
  await expect(symbolSelect).not.toBeDisabled();

  // Check that tradingcopilot.db was loaded (network)
  const dbRequest = await page.waitForResponse(resp =>
    resp.url().includes('tradingcopilot.db') && resp.status() === 200
  );
  expect(dbRequest).toBeTruthy();

  // Select BTC_USD from the dropdown
  await symbolSelect.selectOption('BTC_USD');

  // Wait for dashboard data to update (e.g., cards or table)
  const cards = page.locator('#cards .card');
  await expect(cards.first()).toBeVisible();

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
