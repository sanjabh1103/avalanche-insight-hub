import { defineConfig, devices } from '@playwright/test';

const defaultPort = process.env.PLAYWRIGHT_PHASE6_PORT || '4176';
const baseURL = process.env.TEST_BASE_URL || `http://127.0.0.1:${defaultPort}`;
const webServerTimeoutMs = Number(process.env.PLAYWRIGHT_WEBSERVER_TIMEOUT_MS || '420000');

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { outputFolder: process.env.PLAYWRIGHT_HTML_OUTPUT_DIR || 'playwright-report', open: 'never' }],
    ['list'],
    ['json', { outputFile: process.env.PLAYWRIGHT_JSON_OUTPUT_FILE || 'playwright-results.json' }],
  ],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 10000,
    navigationTimeout: 30000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 720 },
      },
    },
  ],
  webServer: {
    command: 'npm run test:e2e:preview',
    url: baseURL,
    reuseExistingServer: false,
    timeout: webServerTimeoutMs,
  },
});
