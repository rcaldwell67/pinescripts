// Example Playwright test for dashboard homepage
import { test, expect } from '@playwright/test';

test('dashboard loads and shows symbol dropdown', async ({ page }) => {
  await page.goto('http://localhost:3000/docs/index.html');
  await expect(page.locator('#symbolSelect')).toBeVisible();
});
