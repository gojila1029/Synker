/**
 * E2E pages suite (AC-001 through AC-012).
 *
 * Tests validate that all 7 Synker application pages load and display
 * key elements without JavaScript errors or broken network calls.
 *
 * Prerequisites:
 *   - Backend running on http://localhost:8000
 *   - Frontend running on http://localhost:5173
 *   - TEST_EMAIL and TEST_PASSWORD env vars set for a valid Supabase test user
 *
 * Run:
 *   npx playwright test tests/e2e/pages.spec.ts --project=chromium
 */
import { test, expect, Page } from '@playwright/test'

const TEST_EMAIL    = process.env.TEST_EMAIL    ?? ''
const TEST_PASSWORD = process.env.TEST_PASSWORD ?? ''
const skipAuth      = !TEST_EMAIL || !TEST_PASSWORD

// Timeout constants for clarity and consistency
const TIMEOUT_LOGIN = 20_000  // Initial login + app hydration
const TIMEOUT_NAV = 10_000    // Page navigation

async function signIn(page: Page): Promise<void> {
  await page.goto('/')
  await page.waitForSelector('input[type="email"]', { timeout: TIMEOUT_LOGIN })
  await page.fill('input[type="email"]', TEST_EMAIL)
  await page.fill('input[type="password"]', TEST_PASSWORD)
  await page.click('button[type="submit"]')
  // SPA — URL stays at '/'. Wait for the sidebar Sources button to appear after login.
  // Login triggers app initialization (state hydration, initial API calls).
  await page.waitForSelector('button:has-text("Sources")', { timeout: TIMEOUT_LOGIN })
  // Wait for initial data loads to complete before test begins
  await page.waitForLoadState('networkidle')
}

// ── AC-001: Dashboard page loads without errors ────────────────────────────────

test('AC-001: Dashboard page loads and displays content', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await signIn(page)

  // Dashboard is the default screen after login — check for KPI cards or pipeline heading
  await expect(page.locator('[data-testid="dashboard-pipeline-heading"]')).toBeVisible({ timeout: 10_000 })

  // Filter errors: favicon requests and ResizeObserver loops are known non-critical
  // (favicon auto-requested by browser, ResizeObserver is a Chrome observer loop that doesn't block rendering)
  const ignoredErrors = ['favicon', 'ResizeObserver']
  const critical = errors.filter(
    (e) => !ignoredErrors.some(pattern => e.includes(pattern))
  )
  expect(critical, `Console errors: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-002: Sources page loads and displays content ────────────────────────────

test('AC-002: Sources page loads and displays content', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await signIn(page)
  await page.click('[data-testid="nav-sources"]')

  // Wait for Add Source button which is always visible in SourcesScreen
  await expect(page.locator('[data-testid="sources-add-button"]')).toBeVisible({ timeout: 10_000 })

  // Filter errors: favicon requests and ResizeObserver loops are known non-critical
  // (favicon auto-requested by browser, ResizeObserver is a Chrome observer loop that doesn't block rendering)
  const ignoredErrors = ['favicon', 'ResizeObserver']
  const critical = errors.filter(
    (e) => !ignoredErrors.some(pattern => e.includes(pattern))
  )
  expect(critical, `Console errors: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-003: Approval page loads and displays content ────────────────────────────

test('AC-003: Approval page loads and displays content', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await signIn(page)
  await page.click('[data-testid="nav-candidates"]')

  // Wait for either the Review Candidates heading or the Nothing to review empty state
  const reviewHeading = page.locator('[data-testid="approval-review-heading"]')
  const emptyState = page.locator('text=Nothing to review')
  await expect(reviewHeading.or(emptyState)).toBeVisible({ timeout: 10_000 })

  // Filter errors: favicon requests and ResizeObserver loops are known non-critical
  // (favicon auto-requested by browser, ResizeObserver is a Chrome observer loop that doesn't block rendering)
  const ignoredErrors = ['favicon', 'ResizeObserver']
  const critical = errors.filter(
    (e) => !ignoredErrors.some(pattern => e.includes(pattern))
  )
  expect(critical, `Console errors: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-004: Processing Jobs page loads and displays content ──────────────────────

test('AC-004: Processing Jobs page loads and displays content', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await signIn(page)
  await page.click('[data-testid="nav-jobs"]')

  // Wait for either the Processing Jobs heading or job status tabs
  await expect(page.locator('[data-testid="jobs-heading"]').first()).toBeVisible({ timeout: 10_000 })

  // Filter errors: favicon requests and ResizeObserver loops are known non-critical
  // (favicon auto-requested by browser, ResizeObserver is a Chrome observer loop that doesn't block rendering)
  const ignoredErrors = ['favicon', 'ResizeObserver']
  const critical = errors.filter(
    (e) => !ignoredErrors.some(pattern => e.includes(pattern))
  )
  expect(critical, `Console errors: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-005: Knowledge Review page loads and displays content ────────────────────

test('AC-005: Knowledge Review page loads and displays content', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await signIn(page)
  await page.click('[data-testid="nav-review"]')

  // Wait for the Knowledge Review heading (h1 in the left panel) — KnowledgeReviewScreen, line 1256
  const reviewHeading = page.locator('[data-testid="knowledge-review-heading"]')
  const emptyState = page.locator('text=No notes yet')
  await expect(reviewHeading.or(emptyState)).toBeVisible({ timeout: 10_000 })

  // Filter errors: favicon requests and ResizeObserver loops are known non-critical
  // (favicon auto-requested by browser, ResizeObserver is a Chrome observer loop that doesn't block rendering)
  const ignoredErrors = ['favicon', 'ResizeObserver']
  const critical = errors.filter(
    (e) => !ignoredErrors.some(pattern => e.includes(pattern))
  )
  expect(critical, `Console errors: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-006: Vault Browser page loads and displays content ──────────────────────

test('AC-006: Vault Browser page loads and displays content', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await signIn(page)
  await page.click('[data-testid="nav-vault"]')

  // VaultBrowserScreen renders h1 "Vault Browser" heading — unique to this screen
  await expect(page.locator('[data-testid="vault-content"]').first()).toBeVisible({ timeout: 10_000 })

  // Filter errors: favicon requests and ResizeObserver loops are known non-critical
  // (favicon auto-requested by browser, ResizeObserver is a Chrome observer loop that doesn't block rendering)
  const ignoredErrors = ['favicon', 'ResizeObserver']
  const critical = errors.filter(
    (e) => !ignoredErrors.some(pattern => e.includes(pattern))
  )
  expect(critical, `Console errors: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-007: Settings page loads and displays content ───────────────────────────

test('AC-007: Settings page loads and displays content', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await signIn(page)
  await page.click('[data-testid="nav-settings"]')

  // SettingsScreen has an "Obsidian vault path" label unique to this screen
  await expect(page.locator('label:has-text("Obsidian vault path")').first()).toBeVisible({ timeout: 10_000 })

  // Filter errors: favicon requests and ResizeObserver loops are known non-critical
  // (favicon auto-requested by browser, ResizeObserver is a Chrome observer loop that doesn't block rendering)
  const ignoredErrors = ['favicon', 'ResizeObserver']
  const critical = errors.filter(
    (e) => !ignoredErrors.some(pattern => e.includes(pattern))
  )
  expect(critical, `Console errors: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-008: All sidebar buttons are clickable and navigate ──────────────────────

test('AC-008: All sidebar buttons navigate correctly', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  await signIn(page)

  const pages = [
    { testid: 'nav-dashboard', selector: '[data-testid="dashboard-pipeline-heading"]' },
    { testid: 'nav-sources', selector: '[data-testid="sources-add-button"]' },
    { testid: 'nav-candidates', selector: '[data-testid="approval-review-heading"]' },
    { testid: 'nav-jobs', selector: '[data-testid="jobs-heading"]' },
    { testid: 'nav-review', selector: '[data-testid="knowledge-review-heading"]' },
    { testid: 'nav-vault', selector: '[data-testid="vault-content"]' },
    { testid: 'nav-settings', selector: 'label:has-text("Obsidian vault path")' },
  ]

  for (const { testid, selector } of pages) {
    await page.click(`[data-testid="${testid}"]`)
    await expect(page.locator(selector)).toBeVisible({ timeout: 10_000 })
  }
})

// ── AC-009: Active sidebar button shows correct styling ───────────────────────

test('AC-009: Active sidebar button has correct styling', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  await signIn(page)

  // Navigate to Sources
  await page.click('[data-testid="nav-sources"]')
  await page.waitForSelector('[data-testid="sources-add-button"]', { timeout: 10_000 })

  // Check that the Sources button has aria-current="page" attribute (active state)
  const sourcesButton = page.locator('[data-testid="nav-sources"]')
  const ariaCurrent = await sourcesButton.getAttribute('aria-current')

  expect(ariaCurrent).toBe('page')
})

// ── AC-010: Page transitions do not trigger console errors ────────────────────

test('AC-010: Page transitions do not trigger console errors', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })

  await signIn(page)

  // Navigate through multiple pages in sequence
  const navButtons = ['nav-sources', 'nav-candidates', 'nav-jobs', 'nav-review', 'nav-vault', 'nav-settings', 'nav-dashboard']

  for (const testid of navButtons) {
    await page.click(`[data-testid="${testid}"]`)
    await page.waitForLoadState('networkidle')
  }

  const critical = errors.filter(
    (e) => !e.includes('favicon') && !e.includes('ResizeObserver')
  )
  expect(critical, `Console errors during transitions: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-011: Backend health endpoint is reachable ───────────────────────────────

test('AC-011: Backend health endpoint is reachable', async ({ request }) => {
  const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000'
  const resp = await request.get(`${BACKEND}/health`)

  expect(resp.status()).toBe(200)
  const body = await resp.json()
  expect(body.status).toBe('ok')
})

// ── AC-012: All page navigation is read-only (non-destructive) ──────────────────

test('AC-012: Page navigation and element rendering are read-only', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  // Record baseline: no POST/PUT/DELETE calls should occur during navigation
  let mutatingApiCallCount = 0
  page.on('response', (resp) => {
    // Only GET and read-only requests allowed during navigation-only test
    const method = resp.request().method()
    if (['POST', 'PUT', 'DELETE'].includes(method)) {
      mutatingApiCallCount++
    }
  })

  await signIn(page)

  // Navigate through all pages without triggering approval/rejection/submission
  const navButtons = ['nav-sources', 'nav-candidates', 'nav-jobs', 'nav-review', 'nav-vault', 'nav-settings']

  for (const testid of navButtons) {
    await page.click(`[data-testid="${testid}"]`)
    // Load complete before moving to next navigation
    await page.waitForLoadState('networkidle')
  }

  // Verify no data-modifying API calls were made during navigation-only test
  // (navigation should trigger only GET requests, not mutations)
  expect(mutatingApiCallCount, 'Navigation should not trigger POST/PUT/DELETE calls').toBe(0)
})
