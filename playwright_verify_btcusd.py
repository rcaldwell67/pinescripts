import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('file://' + __import__('os').path.abspath('docs/index.html'))
        # Wait for dropdown to populate
        await page.wait_for_selector('#symbolSelect option[value="BTC_USD"]', timeout=5000)
        await page.select_option('#symbolSelect', 'BTC_USD')
        # Wait for summary card or chart to update
        await page.wait_for_selector('.card', timeout=5000)
        # Extract summary card text
        card_text = await page.inner_text('.card')
        print('Summary Card:', card_text)
        # Optionally, check for charts or metrics
        # For example, check if equity chart canvas exists
        equity_chart = await page.query_selector('#equityChart')
        print('Equity chart present:', bool(equity_chart))
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
