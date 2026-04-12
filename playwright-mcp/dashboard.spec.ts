// Example Playwright test for dashboard homepage
import { test, expect } from '@playwright/test';


test('dashboard loads and checks for blank page issue and snapshot timestamp', async ({ page }) => {
  // Collect console errors and warnings
  const consoleMessages = [];
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      consoleMessages.push({ type: msg.type(), text: msg.text() });
    }
  });

  // Use remote site for test
  await page.goto('/docs/');

  // Wait for DOM to settle
  await page.waitForTimeout(2000);

  // Capture screenshot and HTML after load
  await page.screenshot({ path: 'dashboard-initial.png', fullPage: true });
  const htmlInitial = await page.content();
  console.log('PAGE HTML INITIAL START');
  console.log(htmlInitial);
  console.log('PAGE HTML INITIAL END');

  // Check if main content is visible
  const mainVisible = await page.isVisible('main');
  // Cards and symbolSelect are not guaranteed to exist by id, so only check main
  console.log('main visible:', mainVisible);

  // Print all captured console errors and warnings
  if (consoleMessages.length > 0) {
    console.log('PAGE CONSOLE ERRORS/WARNINGS:');
    for (const msg of consoleMessages) {
      console.log(`[${msg.type}] ${msg.text}`);
    }
  } else {
    console.log('No console errors or warnings captured.');
  }

  // Assert that the main dashboard content is visible
  expect(mainVisible).toBeTruthy();

  // Check for the snapshot timestamp chip in the header
  // Looks for a div with class 'chip' containing 'Snapshot:'
  const snapshotChip = await page.locator('header .chip');
  const chipVisible = await snapshotChip.isVisible();
  const chipText = chipVisible ? await snapshotChip.textContent() : '';
  console.log('Snapshot chip visible:', chipVisible, 'Text:', chipText);
  expect(chipVisible).toBeTruthy();
  expect(chipText).toBeTruthy();
  expect(chipText).toMatch(/Snapshot:/);
  // Should not be just 'Snapshot: -'
  expect(chipText?.trim()).not.toBe('Snapshot: -');
});
