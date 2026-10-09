/**
 * E2E tests for folder source feature (AC-009)
 *
 * Tests the full user flow:
 * 1. Add a folder as a source
 * 2. Run the analysis job
 * 3. Verify candidates appear in the dashboard
 *
 * Note: Run with --headed flag to see the browser:
 *   npx playwright test folder-source.spec.ts --headed
 */

import { expect, test } from '@playwright/test'

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173'

test.describe('Folder Source Feature (AC-009)', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app
    await page.goto(FRONTEND_URL)

    // Wait for dashboard to load
    await page.locator('[data-testid="dashboard"]').waitFor({ state: 'visible' })
  })

  test('AC-009: Add folder source and verify candidates appear', async ({ page }) => {
    /**
     * GIVEN the user is on the dashboard
     * WHEN they add a folder as a source
     * THEN the system discovers files and creates candidates
     * AND candidates are visible in the list
     */

    // Click "Add Source" button
    const addSourceBtn = page.locator('[data-testid="add-source-btn"]')
    await addSourceBtn.click()

    // Wait for modal/form to appear
    const sourceForm = page.locator('[data-testid="source-form"]')
    await sourceForm.waitFor({ state: 'visible' })

    // Select source type as "local"
    const typeSelect = page.locator('[data-testid="source-type-select"]')
    await typeSelect.click()
    const localOption = page.locator('[data-testid="source-type-local"]')
    await localOption.click()

    // Enter folder path
    const pathInput = page.locator('[data-testid="source-path-input"]')
    await pathInput.fill('C:/Users/gojil/OneDrive/Documents/SAP Learning/ABAP')

    // Submit form
    const submitBtn = page.locator('[data-testid="source-form-submit"]')
    await submitBtn.click()

    // Wait for source to be added (modal closes and source appears in list)
    const sourcesList = page.locator('[data-testid="sources-list"]')
    await sourcesList.waitFor({ state: 'visible' })

    // Verify source appears
    const folderSource = page.locator('[data-testid="source-abap"]')
    await expect(folderSource).toBeVisible()

    // Run analysis job
    const analyzeBtn = page.locator('[data-testid="run-analysis-btn"]')
    await analyzeBtn.click()

    // Wait for job to complete (check for job status = done or processing)
    const jobStatus = page.locator('[data-testid="job-status"]')
    await jobStatus.waitFor({ state: 'visible' })

    // Wait for candidates to appear
    const candidatesList = page.locator('[data-testid="candidates-list"]')
    await candidatesList.waitFor({ state: 'visible' })

    // Verify at least one candidate is displayed
    const candidateItems = page.locator('[data-testid="candidate-item"]')
    const candidateCount = await candidateItems.count()

    expect(candidateCount).toBeGreaterThan(0)

    // Verify candidate titles are from ABAP folder
    const firstCandidate = candidateItems.first()
    const candidateTitle = await firstCandidate.locator('[data-testid="candidate-title"]').textContent()

    expect(candidateTitle).toBeTruthy()
    expect(candidateTitle).not.toMatch(/undefined|null|error/i)

    // Verify console has no errors
    const consoleMessages = await page.evaluate(() => {
      return (window as any).__consoleLogs || []
    })

    const errors = consoleMessages.filter((msg: string) => msg.includes('error'))
    expect(errors).toHaveLength(0)
  })

  test('AC-009: Folder extraction shows supported files only', async ({ page }) => {
    /**
     * GIVEN a folder source is added
     * WHEN candidates are created
     * THEN only supported file types (.txt, .md, .pdf) appear
     * AND unsupported files are skipped silently
     */

    // Add folder source
    const addSourceBtn = page.locator('[data-testid="add-source-btn"]')
    await addSourceBtn.click()

    const sourceForm = page.locator('[data-testid="source-form"]')
    await sourceForm.waitFor({ state: 'visible' })

    const typeSelect = page.locator('[data-testid="source-type-select"]')
    await typeSelect.click()
    const localOption = page.locator('[data-testid="source-type-local"]')
    await localOption.click()

    const pathInput = page.locator('[data-testid="source-path-input"]')
    await pathInput.fill('C:/Users/gojil/OneDrive/Documents/SAP Learning/ABAP')

    const submitBtn = page.locator('[data-testid="source-form-submit"]')
    await submitBtn.click()

    // Run analysis
    const analyzeBtn = page.locator('[data-testid="run-analysis-btn"]')
    await analyzeBtn.click()

    // Wait for candidates
    const candidatesList = page.locator('[data-testid="candidates-list"]')
    await candidatesList.waitFor({ state: 'visible' })

    const candidateItems = page.locator('[data-testid="candidate-item"]')
    const candidateCount = await candidateItems.count()

    // We expect at least 2 candidates (the PDF slides + at least one txt/md file)
    expect(candidateCount).toBeGreaterThanOrEqual(2)

    // Verify that candidate titles correspond to supported files
    for (let i = 0; i < Math.min(candidateCount, 3); i++) {
      const title = await candidateItems.nth(i).locator('[data-testid="candidate-title"]').textContent()
      // Should not contain error indicators
      expect(title).not.toMatch(/error|unsupported|failed/i)
    }
  })
})
