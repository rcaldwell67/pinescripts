# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: data-views-card-visible.spec.ts >> Data Views card is visible and not hidden
- Location: data-views-card-visible.spec.ts:6:5

# Error details

```
TimeoutError: page.waitForFunction: Timeout 15000ms exceeded.
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
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | // This test checks that the Data Views card is visible and not hidden or overlapped
  4  | 
  5  | 
  6  | test('Data Views card is visible and not hidden', async ({ page }) => {
  7  |   await page.goto('file:///d:/OneDrive/codebase/pinescripts-1/docs/index.html');
  8  | 
  9  |   // Wait for the Data Views card to be present in the DOM
  10 |   const card = await page.locator('#dataViewsCard');
  11 |   await card.waitFor({ state: 'attached', timeout: 10000 });
  12 | 
  13 |   // Wait for the symbol dropdown to be enabled and populated (data loaded)
  14 |   const symbolSelect = card.locator('#symbolSelect');
  15 |   await symbolSelect.waitFor({ state: 'attached', timeout: 15000 });
  16 |   // Wait until the dropdown is enabled and has more than one option
  17 | 
  18 |   try {
> 19 |     await page.waitForFunction(
     |                ^ TimeoutError: page.waitForFunction: Timeout 15000ms exceeded.
  20 |       (sel) => {
  21 |         const el = document.querySelector(sel);
  22 |         return el && !el.disabled && el.options && el.options.length > 1;
  23 |       },
  24 |       '#symbolSelect',
  25 |       { timeout: 15000 }
  26 |     );
  27 |   } catch (e) {
  28 |     // Print debug info if wait fails
  29 |     const isDisabled = await symbolSelect.evaluate(el => el.disabled);
  30 |     const options = await symbolSelect.evaluate(el => Array.from(el.options).map(o => o.value + ':' + o.textContent));
  31 |     console.log('DEBUG: #symbolSelect.disabled =', isDisabled);
  32 |     console.log('DEBUG: #symbolSelect.options =', options);
  33 |     throw e;
  34 |   }
  35 | 
  36 |   // Now check visibility and size
  37 |   await card.waitFor({ state: 'visible', timeout: 10000 });
  38 |   await expect(card).toBeVisible();
  39 | 
  40 |   // Check that the card is not hidden by z-index or opacity
  41 |   const boundingBox = await card.boundingBox();
  42 |   expect(boundingBox).not.toBeNull();
  43 |   expect(boundingBox?.width).toBeGreaterThan(200); // Should be wide
  44 |   expect(boundingBox?.height).toBeGreaterThan(100); // Should be tall enough
  45 | 
  46 |   // Check that the card is not overlapped by header
  47 |   const header = await page.locator('header');
  48 |   const headerBox = await header.boundingBox();
  49 |   if (headerBox && boundingBox) {
  50 |     expect(boundingBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height - 1);
  51 |   }
  52 | 
  53 |   // Check that at least one child control is visible
  54 |   await expect(card.locator('.sym-switcher')).toBeVisible();
  55 |   await expect(card.locator('.mode-switcher')).toBeVisible();
  56 | });
  57 | 
```