# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard.spec.ts >> dashboard loads and shows symbol dropdown
- Location: dashboard.spec.ts:4:5

# Error details

```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000/docs/index.html
Call log:
  - navigating to "http://localhost:3000/docs/index.html", waiting until "load"

```

# Test source

```ts
  1 | // Example Playwright test for dashboard homepage
  2 | import { test, expect } from '@playwright/test';
  3 | 
  4 | test('dashboard loads and shows symbol dropdown', async ({ page }) => {
> 5 |   await page.goto('http://localhost:3000/docs/index.html');
    |              ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000/docs/index.html
  6 |   await expect(page.locator('#symbolSelect')).toBeVisible();
  7 | });
  8 | 
```