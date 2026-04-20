import { test, expect } from '@playwright/test';

// This test validates that Alpaca symbols are available for manual add in the Dashboard,
// and that adding a symbol marks it as Active but not Live.
test('Alpaca symbols available and add sets Active but not Live', async ({ page }) => {
  // Go to the dashboard
  await page.goto('https://rcaldwell67.github.io/pinescripts/docs/');

  // Wait for the Symbols Table section to load
  await expect(page.locator('h2', { hasText: 'Symbols Table' })).toBeVisible();

  // Open the Add Symbol form
  const addButton = page.getByRole('button', { name: /add symbol/i });
  await addButton.click();

  // Wait for the Symbol dropdown to appear
  const symbolSelect = page.locator('form select').first();
  await expect(symbolSelect).toBeVisible();

  // Check that there are many Alpaca symbols in the dropdown (should be > 1000)
  const options = await symbolSelect.locator('option').allTextContents();
  // Remove the placeholder option
  const realOptions = options.filter(opt => opt && !opt.toLowerCase().includes('select'));
  expect(realOptions.length).toBeGreaterThan(1000);

  // Pick the first available symbol
  const symbolToAdd = realOptions[0];
  await symbolSelect.selectOption(symbolToAdd);

  // Optionally fill description (auto-filled)
  const descriptionInput = page.locator('form input');
  await expect(descriptionInput).toBeVisible();

  // Submit the form
  const submitButton = page.getByRole('button', { name: /add symbol/i });
  await submitButton.click();

  // After submit, the form should close and the symbol should appear in the table
  await expect(page.locator('form')).toHaveCount(0);
  // Find the row for the added symbol
  const row = page.locator('table tr', { hasText: symbolToAdd });
  await expect(row).toBeVisible();

  // Check that Is Active is true and Live Enabled is false
  const cells = await row.locator('td').allTextContents();
  // Symbol | Description | Asset Type | Live Enabled | Is Active
  expect(cells[0]).toBe(symbolToAdd);
  expect(cells[3]).toMatch(/false|0/i); // Live Enabled
  expect(cells[4]).toMatch(/true|1/i);  // Is Active
});
