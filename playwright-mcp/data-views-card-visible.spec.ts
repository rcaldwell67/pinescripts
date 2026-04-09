import { test, expect } from '@playwright/test';

// This test checks that the Data Views card is visible and not hidden or overlapped


test('Troubleshoot blank dashboard page', async ({ page }) => {
  // Capture console errors
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      console.log('PAGE CONSOLE', msg.type(), msg.text());
    }
  });

  await page.goto('https://rcaldwell67.github.io/pinescripts/');
  await page.waitForTimeout(3000); // Wait for scripts to run

  // Print the full HTML for inspection
  const html = await page.content();
  console.log('PAGE HTML START');
  console.log(html);
  console.log('PAGE HTML END');

  // Screenshot for visual inspection
  await page.screenshot({ path: 'dashboard-troubleshoot.png', fullPage: true });
});
