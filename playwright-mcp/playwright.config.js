

module.exports = {
  testDir: './',
  timeout: 30000,
  retries: 0,
  use: {
    headless: true,
    baseURL: 'https://rcaldwell67.github.io/pinescripts',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
};
