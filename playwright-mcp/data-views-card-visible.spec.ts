import { test, expect } from '@playwright/test';

// This test checks that the Data Views card is visible and not hidden or overlapped


test('Data Views card is visible and not hidden', async ({ page }) => {
  await page.goto('https://rcaldwell67.github.io/pinescripts/');

  // Wait for the Data Views card to be present in the DOM
  const card = await page.locator('#dataViewsCard');
  await card.waitFor({ state: 'attached', timeout: 10000 });

  // Wait for the symbol dropdown to be enabled and populated (data loaded)
  const symbolSelect = card.locator('#symbolSelect');
  await symbolSelect.waitFor({ state: 'attached', timeout: 15000 });
  // Wait until the dropdown is enabled and has more than one option

  try {
    await page.waitForFunction(
      (sel) => {
        const el = document.querySelector(sel);
        return el && !el.disabled && el.options && el.options.length > 1;
      },
      '#symbolSelect',
      { timeout: 15000 }
    );
  } catch (e) {
    // Print debug info if wait fails
    const isDisabled = await symbolSelect.evaluate(el => el.disabled);
    const options = await symbolSelect.evaluate(el => Array.from(el.options).map(o => o.value + ':' + o.textContent));
    console.log('DEBUG: #symbolSelect.disabled =', isDisabled);
    console.log('DEBUG: #symbolSelect.options =', options);
    throw e;
  }

  // Now check visibility and size
  await card.waitFor({ state: 'visible', timeout: 10000 });
  await expect(card).toBeVisible();

  // Check that the card is not hidden by z-index or opacity
  const boundingBox = await card.boundingBox();
  expect(boundingBox).not.toBeNull();
  expect(boundingBox?.width).toBeGreaterThan(200); // Should be wide
  expect(boundingBox?.height).toBeGreaterThan(100); // Should be tall enough

  // Check that the card is not overlapped by header
  const header = await page.locator('header');
  const headerBox = await header.boundingBox();
  if (headerBox && boundingBox) {
    expect(boundingBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height - 1);
  }

  // Check that at least one child control is visible
  await expect(card.locator('.sym-switcher')).toBeVisible();
  await expect(card.locator('.mode-switcher')).toBeVisible();
});
