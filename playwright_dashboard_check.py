from playwright.sync_api import sync_playwright

# Path to your dashboard HTML file
DASHBOARD_PATH = 'docs/index.html'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(f'file:///{DASHBOARD_PATH}', wait_until='load')
    print('Dashboard loaded.')

    # Wait for the symbol dropdown to be enabled
    page.wait_for_selector('#symbolSelect:not([disabled])', timeout=10000)
    print('Symbol dropdown enabled.')

    # Get all symbol options
    options = page.query_selector_all('#symbolSelect option')
    symbols = [opt.inner_text() for opt in options if opt.get_attribute('value')]
    print('Symbols found:', symbols)

    # Select BTC_USD if present
    if any('BTC_USD' in s for s in symbols):
        page.select_option('#symbolSelect', value='BTC_USD')
        print('Selected BTC_USD.')
        # Wait for dashboard data to attempt to load
        page.wait_for_timeout(2000)
        # Check for cards or error messages
        cards = page.query_selector_all('.card')
        if cards:
            print('Backtest data cards found:', len(cards))
        else:
            print('No backtest data cards found.')
        # Check for no data notice
        no_data = page.is_visible('#noDataNotice')
        if no_data:
            print('No Data Is Available For That Selection (notice shown)')
    else:
        print('BTC_USD not found in symbol dropdown.')

    browser.close()
