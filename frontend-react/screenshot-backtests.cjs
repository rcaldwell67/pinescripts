const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('http://localhost:5173/pinescripts/');
  await page.click('text=Backtests');
  await page.waitForSelector('text=Backtests (v6) - Active Symbols', { timeout: 5000 });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: 'frontend-react/backtest-section.png', fullPage: true });
  await browser.close();
})();
