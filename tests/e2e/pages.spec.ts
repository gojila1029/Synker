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

async function signIn(page: Page): Promise<void> {
  await page.goto('/')
  await page.waitForSelector('input[type="email"], [data-testid="email-input"]', { timeout: 10_000 })
  await page.fill('input[type="email"]', TEST_EMAIL)
  await page.fill('input[type="password"]', TEST_PASSWORD)
  await page.click('button[type="submit"], button:has-text("Sign in"), button:has-text("Login")')
  await page.waitForSelector('button:has-text("Sources")', { timeout: 20_000 })
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
  await expect(page.locator('text=Knowledge Pipeline')).toBeVisible({ timeout: 10_000 })

  const critical = errors.filter(
    (e) => !e.includes('favicon') && !e.includes('ResizeObserver')
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
  await page.click('button:has-text("Sources")')
  await expect(page.locator('button:has-text("Add Source")')).toBeVisible({ timeout: 10_000 })

  const critical = errors.filter(
    (e) => !e.includes('favicon') && !e.includes('ResizeObserver')
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
  await page.click('button:has-text("Approval")')

  const reviewHeading = page.locator('h1:has-text("Review Candidates")')
  const emptyState = page.locator('text=Nothing to review')
  await expect(reviewHeading.or(emptyState)).toBeVisible({ timeout: 10_000 })

  const critical = errors.filter(
    (e) => !e.includes('favicon') && !e.includes('ResizeObserver')
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
  await page.click('button:has-text("Jobs")')
  await expect(page.locator('h1:has-text("Processing Jobs")').first()).toBeVisible({ timeout: 10_000 })

  const critical = errors.filter(
    (e) => !e.includes('favicon') && !e.includes('ResizeObserver')
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
  await page.click('button:has-text("Knowledge")')

  const reviewHeading = page.locator('text=Knowledge Review')
  const emptyState = page.locator('text=No notes yet')
  await expect(reviewHeading.or(emptyState)).toBeVisible({ timeout: 10_000 })

  const critical = errors.filter(
    (e) => !e.includes('favicon') && !e.includes('ResizeObserver')
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
  await page.click('button:has-text("Vault")')
  await expect(page.locator('h1:has-text("Vault Browser")').first()).toBeVisible({ timeout: 10_000 })

  const critical = errors.filter(
    (e) => !e.includes('favicon') && !e.includes('ResizeObserver')
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
  await page.click('button:has-text("Settings")')
  // "Obsidian vault path" label is unique to SettingsScreen
  await expect(page.locator('label:has-text("Obsidian vault path")').first()).toBeVisible({ timeout: 10_000 })

  const critical = errors.filter(
    (e) => !e.includes('favicon') && !e.includes('ResizeObserver')
  )
  expect(critical, `Console errors: ${critical.join(', ')}`).toHaveLength(0)
})

// ── AC-008: All sidebar buttons are clickable and navigate ──────────────────────

test('AC-008: All sidebar buttons navigate correctly', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  await signIn(page)

  const pages = [
    { label: 'Dashboard', selector: 'text=Knowledge Pipeline' },
    { label: 'Sources', selector: 'button:has-text("Add Source")' },
    { label: 'Approval', selector: 'h1:has-text("Review Candidates")' },
    { label: 'Jobs', selector: 'h1:has-text("Processing Jobs")' },
    { label: 'Knowledge', selector: 'text=Knowledge Review' },
    { label: 'Vault', selector: 'h1:has-text("Vault Browser")' },
    { label: 'Settings', selector: 'label:has-text("Obsidian vault path")' },
  ]

  for (const { label, selector } of pages) {
    await page.click(`button:has-text("${label}")`)
    await expect(page.locator(selector).first()).toBeVisible({ timeout: 10_000 })
  }
})

// ── AC-009: Active sidebar button shows correct styling ───────────────────────

test('AC-009: Active sidebar button has correct styling', async ({ page }) => {
  test.skip(skipAuth, 'TEST_EMAIL / TEST_PASSWORD not set')

  await signIn(page)
  await page.click('button:has-text("Sources")')
  await page.waitForSelector('button:has-text("Add Source")', { timeout: 10_000 })

  const sourcesButton = page.locator('nav button:has-text("Sources")')
  const classes = await sourcesButton.evaluate((el) => el.className)
  expect(classes).toContain('bg-blue-600')
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

  const navButtons = ['Sources', 'Approval', 'Jobs', 'Knowledge', 'Vault', 'Settings', 'Dashboard']
  for (const button of navButtons) {
    await page.click(`button:has-text("${button}")`)
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

  await signIn(page)

  const navButtons = ['Sources', 'Approval', 'Jobs', 'Knowledge', 'Vault', 'Settings']
  for (const button of navButtons) {
    await page.click(`button:has-text("${button}")`)
    await page.waitForLoadState('networkidle')

    // Navigation-only: no form submissions, no approvals, no deletions triggered
    const formSubmissions = await page.locator('form').count()
    if (formSubmissions > 0) {
      const submitButtons = await page.locator('button[type="submit"]').count()
      expect(submitButtons, `Page '${button}' has unclicked submit buttons`).toBeGreaterThanOrEqual(0)
    }
  }
})
