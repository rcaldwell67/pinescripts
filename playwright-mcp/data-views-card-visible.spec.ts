import { test, expect } from '@playwright/test';

// This test checks that the Data Views card is visible and not hidden or overlapped


test('Troubleshoot blank dashboard page', async ({ page }) => {
  // Collect console errors and warnings
  const consoleMessages = [];
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      consoleMessages.push({ type: msg.type(), text: msg.text() });
    }
  });

  await page.goto('https://rcaldwell67.github.io/pinescripts/');

  // Immediately capture screenshot and HTML after load
  await page.screenshot({ path: 'dashboard-initial.png', fullPage: true });
  const htmlInitial = await page.content();
  console.log('PAGE HTML INITIAL START');
  console.log(htmlInitial);
  console.log('PAGE HTML INITIAL END');

  // Wait for 3 seconds to allow blackout to occur
  await page.waitForTimeout(3000);

  // Capture screenshot and HTML after delay
  await page.screenshot({ path: 'dashboard-after-delay.png', fullPage: true });
  const htmlAfter = await page.content();
  console.log('PAGE HTML AFTER DELAY START');
  console.log(htmlAfter);
  console.log('PAGE HTML AFTER DELAY END');

  // Print all captured console errors and warnings
  if (consoleMessages.length > 0) {
    console.log('PAGE CONSOLE ERRORS/WARNINGS:');
    for (const msg of consoleMessages) {
      console.log(`[${msg.type}] ${msg.text}`);
    }
  } else {
    console.log('No console errors or warnings captured.');
  }
});
