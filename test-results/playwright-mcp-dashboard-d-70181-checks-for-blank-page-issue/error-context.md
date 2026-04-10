# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: playwright-mcp\dashboard.spec.ts >> dashboard loads and checks for blank page issue
- Location: playwright-mcp\dashboard.spec.ts:5:5

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - banner [ref=e2]:
    - generic [ref=e3]:
      - heading "APM Dashboard" [level=1] [ref=e4]
      - generic [ref=e5]: Adaptive Pullback Momentum
  - main [ref=e6]
```

# Test source

```ts
  1  | // Example Playwright test for dashboard homepage
  2  | import { test, expect } from '@playwright/test';
  3  | 
  4  | 
  5  | test('dashboard loads and checks for blank page issue', async ({ page }) => {
  6  |   // Collect console errors and warnings
  7  |   const consoleMessages = [];
  8  |   page.on('console', msg => {
  9  |     if (msg.type() === 'error' || msg.type() === 'warning') {
  10 |       consoleMessages.push({ type: msg.type(), text: msg.text() });
  11 |     }
  12 |   });
  13 | 
  14 |   await page.goto('http://127.0.0.1:5500/docs/');
  15 | 
  16 |   // Wait for DOM to settle
  17 |   await page.waitForTimeout(2000);
  18 | 
  19 |   // Capture screenshot and HTML after load
  20 |   await page.screenshot({ path: 'dashboard-initial.png', fullPage: true });
  21 |   const htmlInitial = await page.content();
  22 |   console.log('PAGE HTML INITIAL START');
  23 |   console.log(htmlInitial);
  24 |   console.log('PAGE HTML INITIAL END');
  25 | 
  26 |   // Check if main content is visible
  27 |   const mainVisible = await page.isVisible('main');
  28 |   const cardsVisible = await page.isVisible('#cards');
  29 |   const symbolSelectVisible = await page.isVisible('#symbolSelect');
  30 |   console.log('main visible:', mainVisible);
  31 |   console.log('#cards visible:', cardsVisible);
  32 |   console.log('#symbolSelect visible:', symbolSelectVisible);
  33 | 
  34 |   // Print all captured console errors and warnings
  35 |   if (consoleMessages.length > 0) {
  36 |     console.log('PAGE CONSOLE ERRORS/WARNINGS:');
  37 |     for (const msg of consoleMessages) {
  38 |       console.log(`[${msg.type}] ${msg.text}`);
  39 |     }
  40 |   } else {
  41 |     console.log('No console errors or warnings captured.');
  42 |   }
  43 | 
  44 |   // Assert that the main dashboard content is visible
  45 |   expect(mainVisible).toBeTruthy();
> 46 |   expect(cardsVisible).toBeTruthy();
     |                        ^ Error: expect(received).toBeTruthy()
  47 |   expect(symbolSelectVisible).toBeTruthy();
  48 | });
  49 | 
```