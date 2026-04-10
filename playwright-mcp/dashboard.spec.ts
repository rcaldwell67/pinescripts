// Example Playwright test for dashboard homepage
import { test, expect } from '@playwright/test';


test('dashboard loads and checks for blank page issue', async ({ page }) => {
  // Collect console errors and warnings
  const consoleMessages = [];
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      consoleMessages.push({ type: msg.type(), text: msg.text() });
    }
  });

  await page.goto('http://127.0.0.1:5500/docs/');

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
  const cardsVisible = await page.isVisible('#cards');
  const symbolSelectVisible = await page.isVisible('#symbolSelect');
  console.log('main visible:', mainVisible);
  console.log('#cards visible:', cardsVisible);
  console.log('#symbolSelect visible:', symbolSelectVisible);

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
  expect(cardsVisible).toBeTruthy();
  expect(symbolSelectVisible).toBeTruthy();
});
