import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  globalSetup: 'tests/auth.setup.ts',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on',
    headless: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      testMatch: ['e2e.spec.ts', 'action-card.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium-authenticated',
      testMatch: ['map.spec.ts'],
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'tests/.auth/storageState.json',
      },
    },
  ],
  webServer: {
    // e2e_up.sh starts the full Docker stack, seeds demo data, waits for the
    // backend, then execs into vite preview on port 4173. Playwright manages
    // the process lifecycle (SIGTERM after tests).
    command: 'bash ../scripts/e2e_up.sh',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
