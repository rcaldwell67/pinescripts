# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: ticker-symbol-filter-github.spec.ts >> ticker updates for selected symbol on GitHub Pages
- Location: ticker-symbol-filter-github.spec.ts:3:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('#symbolSelect')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('#symbolSelect')

```

# Page snapshot

```yaml
- generic [ref=e2]:
  - heading "404" [level=1] [ref=e3]
  - paragraph [ref=e4]:
    - strong [ref=e5]: File not found
  - paragraph [ref=e6]: The site configured at this address does not contain the requested file.
  - paragraph [ref=e7]:
    - text: If this is your site, make sure that the filename case matches the URL as well as any file permissions.
    - text: For root URLs (like
    - code [ref=e8]: http://example.com/
    - text: ) you must provide an
    - code [ref=e9]: index.html
    - text: file.
  - paragraph [ref=e10]:
    - link "Read the full documentation" [ref=e11] [cursor=pointer]:
      - /url: https://help.github.com/pages/
    - text: for more information about using
    - strong [ref=e12]: GitHub Pages
    - text: .
  - generic [ref=e13]:
    - link "GitHub Status" [ref=e14] [cursor=pointer]:
      - /url: https://githubstatus.com
    - text: —
    - link "@githubstatus" [ref=e15] [cursor=pointer]:
      - /url: https://twitter.com/githubstatus
  - link [ref=e16] [cursor=pointer]:
    - /url: /
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test('ticker updates for selected symbol on GitHub Pages', async ({ page }) => {
  4  |   // Replace with your actual GitHub Pages URL
  5  |   const githubPagesUrl = 'https://rcaldwell67.github.io/pinescripts/docs/index.html';
  6  |   await page.goto(githubPagesUrl);
  7  | 
  8  |   // Wait for the symbol dropdown to be visible
  9  |   const symbolSelect = page.locator('#symbolSelect');
> 10 |   await expect(symbolSelect).toBeVisible();
     |                              ^ Error: expect(locator).toBeVisible() failed
  11 | 
  12 |   // Select a symbol (e.g., BTCUSD)
  13 |   await symbolSelect.selectOption('BTCUSD');
  14 | 
  15 |   // Wait for the ticker to update
  16 |   const tickerTrack = page.locator('#transactionTickerTrack .ticker-item');
  17 |   await expect(tickerTrack).toBeVisible();
  18 | 
  19 |   // Check that the ticker only shows the selected symbol
  20 |   const tickerSymbols = await page.$$eval('#transactionTickerTrack .ticker-symbol', els => els.map(e => e.textContent?.trim()));
  21 |   expect(tickerSymbols.length).toBeGreaterThan(0);
  22 |   for (const symbol of tickerSymbols) {
  23 |     expect(symbol).toBe('BTCUSD');
  24 |   }
  25 | });
```