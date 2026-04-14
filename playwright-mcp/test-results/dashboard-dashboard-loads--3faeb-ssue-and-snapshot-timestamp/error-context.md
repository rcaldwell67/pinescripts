# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard.spec.ts >> dashboard loads and checks for blank page issue and snapshot timestamp
- Location: dashboard.spec.ts:5:5

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Page snapshot

```yaml
- generic [ref=e2]:
  - heading "404" [level=1] [ref=e3]
  - paragraph [ref=e4]:
    - strong [ref=e5]: There isn't a GitHub Pages site here.
  - paragraph [ref=e6]:
    - text: If you're trying to publish one,
    - link "read the full documentation" [ref=e7] [cursor=pointer]:
      - /url: https://help.github.com/pages/
    - text: to learn how to set up
    - strong [ref=e8]: GitHub Pages
    - text: for your repository, organization, or user account.
  - generic [ref=e9]:
    - link "GitHub Status" [ref=e10] [cursor=pointer]:
      - /url: https://githubstatus.com
    - text: —
    - link "@githubstatus" [ref=e11] [cursor=pointer]:
      - /url: https://twitter.com/githubstatus
  - link [ref=e12] [cursor=pointer]:
    - /url: /
```

# Test source

```ts
  1  | // Example Playwright test for dashboard homepage
  2  | import { test, expect } from '@playwright/test';
  3  | 
  4  | 
  5  | test('dashboard loads and checks for blank page issue and snapshot timestamp', async ({ page }) => {
  6  |   // Collect console errors and warnings
  7  |   const consoleMessages = [];
  8  |   page.on('console', msg => {
  9  |     if (msg.type() === 'error' || msg.type() === 'warning') {
  10 |       consoleMessages.push({ type: msg.type(), text: msg.text() });
  11 |     }
  12 |   });
  13 | 
  14 |   // Use remote site for test
  15 |   await page.goto('/docs/');
  16 | 
  17 |   // Wait for DOM to settle
  18 |   await page.waitForTimeout(2000);
  19 | 
  20 |   // Capture screenshot and HTML after load
  21 |   await page.screenshot({ path: 'dashboard-initial.png', fullPage: true });
  22 |   const htmlInitial = await page.content();
  23 |   console.log('PAGE HTML INITIAL START');
  24 |   console.log(htmlInitial);
  25 |   console.log('PAGE HTML INITIAL END');
  26 | 
  27 |   // Check if main content is visible
  28 |   const mainVisible = await page.isVisible('main');
  29 |   // Cards and symbolSelect are not guaranteed to exist by id, so only check main
  30 |   console.log('main visible:', mainVisible);
  31 | 
  32 |   // Print all captured console errors and warnings
  33 |   if (consoleMessages.length > 0) {
  34 |     console.log('PAGE CONSOLE ERRORS/WARNINGS:');
  35 |     for (const msg of consoleMessages) {
  36 |       console.log(`[${msg.type}] ${msg.text}`);
  37 |     }
  38 |   } else {
  39 |     console.log('No console errors or warnings captured.');
  40 |   }
  41 | 
  42 |   // Assert that the main dashboard content is visible
> 43 |   expect(mainVisible).toBeTruthy();
     |                       ^ Error: expect(received).toBeTruthy()
  44 | 
  45 |   // Check for the snapshot timestamp chip in the header
  46 |   // Looks for a div with class 'chip' containing 'Snapshot:'
  47 |   const snapshotChip = await page.locator('header .chip');
  48 |   const chipVisible = await snapshotChip.isVisible();
  49 |   const chipText = chipVisible ? await snapshotChip.textContent() : '';
  50 |   console.log('Snapshot chip visible:', chipVisible, 'Text:', chipText);
  51 |   expect(chipVisible).toBeTruthy();
  52 |   expect(chipText).toBeTruthy();
  53 |   expect(chipText).toMatch(/Snapshot:/);
  54 |   // Should not be just 'Snapshot: -'
  55 |   expect(chipText?.trim()).not.toBe('Snapshot: -');
  56 | });
  57 | 
```