#!/usr/bin/env python3
"""Playwright check: validate BTC v3 'Net Return' on the docs dashboard.

Run after starting a static server serving the `docs/` directory on http://localhost:8000
This script expects Playwright to be installed in the current Python environment.
"""
from playwright.sync_api import sync_playwright
import sys

URL = "http://localhost:8000/index.html"
EXPECTED = "+7.41%"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Opening", URL)
        page.goto(URL, timeout=60000)

        try:
            # Wait until the comparison table has a populated Net Return value for v3
            page.wait_for_function("""
() => {
  const t = document.querySelector('#cmpTable');
  if (!t) return false;
  const headers = Array.from(t.querySelectorAll('thead th')).map(h=>h.textContent.trim());
  const v3Index = headers.findIndex(h => h.split('·')[0].trim().startsWith('v3'));
  if (v3Index === -1) return false;
  const rows = Array.from(t.querySelectorAll('tbody tr')).map(r => Array.from(r.querySelectorAll('td')).map(c=>c.textContent.trim()));
  const netRow = rows.find(r => r[0] === 'Net Return');
  if (!netRow) return false;
  const val = netRow[v3Index];
  return !!val && val !== '—';
}
""", timeout=60000)

            val = page.evaluate("""
() => {
  const t = document.querySelector('#cmpTable');
  const headers = Array.from(t.querySelectorAll('thead th')).map(h=>h.textContent.trim());
  const v3Index = headers.findIndex(h => h.split('·')[0].trim().startsWith('v3'));
  const rows = Array.from(t.querySelectorAll('tbody tr')).map(r => Array.from(r.querySelectorAll('td')).map(c=>c.textContent.trim()));
  const netRow = rows.find(r=>r[0]==='Net Return');
  return netRow && netRow[v3Index];
}
""")

            print_val = f"Found Net Return for v3: {val}"
            print(print_val)
            if val != EXPECTED:
                print(f"Mismatch — expected {EXPECTED}")
                browser.close()
                return 2
            print(f"OK — Net Return matches expected {EXPECTED}")
            browser.close()
            return 0
        except Exception as e:
            print("Error waiting for Net Return:", e)
            browser.close()
            return 3

if __name__ == '__main__':
    sys.exit(main())
#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import time
import sys
from pathlib import Path

SERVE_HOST = '127.0.0.1'
SERVE_PORT = 8000

def serve_docs(directory, host=SERVE_HOST, port=SERVE_PORT):
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(*args, directory=str(directory), **kwargs)
    httpd = HTTPServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread

def run_check(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until='networkidle')
        # Wait for comparison table to render
        page.wait_for_selector('#cmpTable', timeout=20000)
        result = page.evaluate('''() => {
            const table = document.getElementById('cmpTable');
            if (!table) return {error:'no-cmpTable'};
            const headers = Array.from(table.querySelectorAll('thead th')).map(h=>h.textContent.trim());
            const v3Index = headers.findIndex(t => /v3\b/.test(t));
            const rows = table.querySelectorAll('tbody tr');
            for (const row of rows) {
                const label = row.querySelector('td')?.textContent?.trim();
                if (label === 'Net Return') {
                    const cells = Array.from(row.querySelectorAll('td'));
                    return {text: cells[v3Index] ? cells[v3Index].textContent.trim() : null, headers, v3Index};
                }
            }
            return {error:'row-not-found', headers};
        }''')
        browser.close()
        return result

def main():
    repo_root = Path(__file__).resolve().parents[2]
    docs_dir = repo_root / 'docs'
    if not docs_dir.exists():
        print('docs/ directory not found at', docs_dir, file=sys.stderr)
        sys.exit(2)

    httpd, thread = serve_docs(docs_dir)
    time.sleep(0.5)
    url = f'http://{SERVE_HOST}:{SERVE_PORT}/index.html'
    print('Serving', docs_dir, 'at', url)
    try:
        res = run_check(url)
        print('Playwright result:', res)
        if res.get('error'):
            print('ERROR:', res['error'])
            sys.exit(3)
        txt = res.get('text')
        if not txt:
            print('No value found for v3 Net Return')
            sys.exit(4)
        # Normalize and parse percentage
        val = txt.replace('%','').replace('+','').replace(',','').strip()
        try:
            pct = float(val)
        except Exception as e:
            print('Failed to parse percentage:', txt, e)
            sys.exit(5)
        print(f'v3 Net Return: {pct}%')
        # Simple validation: expect >6.5 (we updated to ~7.41)
        if pct < 6.5:
            print('Validation failed: Net Return is lower than expected (<' + '6.5%)')
            sys.exit(6)
        print('Validation passed')
        sys.exit(0)
    finally:
        httpd.shutdown()
        thread.join(timeout=1)

if __name__ == '__main__':
    main()
