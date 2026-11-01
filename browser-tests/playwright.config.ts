import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  globalTimeout: 180_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: !!process.env.CI,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { ...devices['Desktop Chrome'], trace: 'retain-on-failure', screenshot: 'only-on-failure', serviceWorkers: 'block' },
  webServer: { command: 'python3 tests/server.py', url: 'http://127.0.0.1:4182/healthz', reuseExistingServer: false, timeout: 60_000 },
  projects: [{ name: 'StuffApp', use: { baseURL: 'http://127.0.0.1:4182' } }],
});
