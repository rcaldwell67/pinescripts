# Playwright configuration for MCP dashboard testing
# See https://playwright.dev/docs/test-configuration

module.exports = {
  testDir: './',
  timeout: 30000,
  retries: 0,
  use: {
    headless: true,
    baseURL: 'http://localhost:3000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
};
