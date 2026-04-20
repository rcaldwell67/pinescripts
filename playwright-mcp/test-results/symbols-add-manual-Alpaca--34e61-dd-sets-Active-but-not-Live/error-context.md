# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: symbols-add-manual.spec.ts >> Alpaca symbols available and add sets Active but not Live
- Location: symbols-add-manual.spec.ts:5:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('h2').filter({ hasText: 'Symbols Table' })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('h2').filter({ hasText: 'Symbols Table' })

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
  3  | // This test validates that Alpaca symbols are available for manual add in the Dashboard,
  4  | // and that adding a symbol marks it as Active but not Live.
  5  | test('Alpaca symbols available and add sets Active but not Live', async ({ page }) => {
  6  |   // Go to the dashboard
  7  |   await page.goto('https://rcaldwell67.github.io/pinescripts/docs/');
  8  | 
  9  |   // Wait for the Symbols Table section to load
> 10 |   await expect(page.locator('h2', { hasText: 'Symbols Table' })).toBeVisible();
     |                                                                  ^ Error: expect(locator).toBeVisible() failed
  11 | 
  12 |   // Open the Add Symbol form
  13 |   const addButton = page.getByRole('button', { name: /add symbol/i });
  14 |   await addButton.click();
  15 | 
  16 |   // Wait for the Symbol dropdown to appear
  17 |   const symbolSelect = page.locator('form select').first();
  18 |   await expect(symbolSelect).toBeVisible();
  19 | 
  20 |   // Check that there are many Alpaca symbols in the dropdown (should be > 1000)
  21 |   const options = await symbolSelect.locator('option').allTextContents();
  22 |   // Remove the placeholder option
  23 |   const realOptions = options.filter(opt => opt && !opt.toLowerCase().includes('select'));
  24 |   expect(realOptions.length).toBeGreaterThan(1000);
  25 | 
  26 |   // Pick the first available symbol
  27 |   const symbolToAdd = realOptions[0];
  28 |   await symbolSelect.selectOption(symbolToAdd);
  29 | 
  30 |   // Optionally fill description (auto-filled)
  31 |   const descriptionInput = page.locator('form input');
  32 |   await expect(descriptionInput).toBeVisible();
  33 | 
  34 |   // Submit the form
  35 |   const submitButton = page.getByRole('button', { name: /add symbol/i });
  36 |   await submitButton.click();
  37 | 
  38 |   // After submit, the form should close and the symbol should appear in the table
  39 |   await expect(page.locator('form')).toHaveCount(0);
  40 |   // Find the row for the added symbol
  41 |   const row = page.locator('table tr', { hasText: symbolToAdd });
  42 |   await expect(row).toBeVisible();
  43 | 
  44 |   // Check that Is Active is true and Live Enabled is false
  45 |   const cells = await row.locator('td').allTextContents();
  46 |   // Symbol | Description | Asset Type | Live Enabled | Is Active
  47 |   expect(cells[0]).toBe(symbolToAdd);
  48 |   expect(cells[3]).toMatch(/false|0/i); // Live Enabled
  49 |   expect(cells[4]).toMatch(/true|1/i);  // Is Active
  50 | });
  51 | 
```