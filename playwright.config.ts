import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E configuration for Synker.
 *
 * Prerequisites:
 *   - Backend:  http://localhost:8000  (cd backend && uv run uvicorn app.main:app --reload)
 *   - Frontend: http://localhost:5173  (npm run dev)
 *
 * Run smoke suite:
 *   npx playwright test tests/e2e/ --project=chromium
 *
 * Run headed (visual):
 *   npx playwright test --headed
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: process.env.FRONTEND_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium-staging',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'https://synker-frontend-staging.up.railway.app',
      },
    },
  ],
})
