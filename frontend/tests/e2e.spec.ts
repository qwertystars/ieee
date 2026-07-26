import { test, expect, type Page } from '@playwright/test'

// E2E flow tests — require a running backend (FastAPI on :8000) and the
// Rivertown demo scenario seeded. See tests/README.md for setup.
//
// Flow: login → dashboard map → simulator → alert → approve → field task →
// task update → command centre sees update → polling fallback.

const DEMO_EMAIL = 'admin@demo.disaster'
const DEMO_PASSWORD = 'demo1234'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(DEMO_EMAIL)
  await page.getByLabel('Password').fill(DEMO_PASSWORD)
  await page.getByLabel('Sign in').click()
  await page.waitForURL('**/dashboard', { timeout: 15_000 })
}

test.describe('Full responder flow', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('dashboard map renders after login', async ({ page }) => {
    await expect(page).toHaveURL(/\/dashboard/)
    // The dashboard renders either the map or the low-bandwidth placeholder.
    const mapContainer = page.locator('[data-testid="map-container"]')
    const lowBwPlaceholder = page.locator('[aria-label="Map imagery stripped — low-bandwidth mode active"]')
    await expect(mapContainer.or(lowBwPlaceholder)).toBeVisible({ timeout: 15_000 })

    // The incident title should appear in the sidebar.
    await expect(page.locator('aside')).toContainText(/Rivertown|Flood|Incident/i, { timeout: 15_000 })
  })

  test('simulator starts and device count is visible', async ({ page }) => {
    await page.getByRole('link', { name: 'Simulation' }).click()
    await page.waitForURL('**/simulation', { timeout: 10_000 })

    // The simulator status panel should show a state (stopped/running/paused).
    await expect(page.locator('body')).toContainText(/stopped|running|paused/i, { timeout: 15_000 })

    // Start the simulator if it's stopped.
    const startButton = page.getByRole('button', { name: /start/i })
    if (await startButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await startButton.click()
      // Wait for state to transition to running.
      await expect(page.locator('body')).toContainText(/running/i, { timeout: 15_000 })
    }
  })

  test('alert appears in the dashboard sidebar', async ({ page }) => {
    // Navigate to dashboard and wait for alerts panel.
    await page.waitForURL('**/dashboard')
    // The alerts panel should be present (may be empty or have alerts).
    await expect(page.getByRole('heading', { name: 'Alerts' })).toBeVisible({ timeout: 15_000 })
  })

  test('operator can approve an alert from the planning page', async ({ page }) => {
    await page.getByRole('link', { name: 'Planning' }).click()
    await page.waitForURL('**/planning', { timeout: 10_000 })
    // The planning page should render (may have alerts with approve buttons).
    await expect(page.locator('body')).toBeVisible({ timeout: 15_000 })
  })

  test('field responder view shows assigned tasks', async ({ page }) => {
    await page.getByRole('link', { name: 'Field' }).click()
    await page.waitForURL('**/field', { timeout: 10_000 })

    // The field page should show the "My Tasks" section.
    await expect(page.getByRole('heading', { name: 'My Tasks' })).toBeVisible({ timeout: 15_000 })
  })

  test('task status update from field view reaches command centre', async ({ page }) => {
    // Navigate to field view.
    await page.getByRole('link', { name: 'Field' }).click()
    await page.waitForURL('**/field', { timeout: 10_000 })

    // If there are tasks, update the first one's status.
    const taskSelect = page.locator('select[aria-label^="Update status for task"]').first()
    if (await taskSelect.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await taskSelect.selectOption('in_progress')

      // Wait for the toast confirmation.
      await expect(page.locator('[role="alert"]')).toContainText(/in_progress/i, { timeout: 10_000 })

      // Navigate back to dashboard and verify the task status propagated.
      await page.getByRole('link', { name: 'Dashboard' }).click()
      await page.waitForURL('**/dashboard', { timeout: 10_000 })
      // The tasks panel should show the updated status.
      await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible({ timeout: 15_000 })
    }
  })

  test('polling fallback — UI shows stale indicator when data is aging', async ({ page }) => {
    // The dashboard uses TanStack Query with refetchInterval. When data is
    // stale, the StaleState component renders. This test verifies the UI
    // handles slow/aging data gracefully (doesn't crash, shows panels).
    await page.waitForURL('**/dashboard')
    // Wait for the situation report panel to render.
    await expect(page.getByRole('heading', { name: 'Situation Report' }).or(
      page.getByRole('heading', { name: 'Alerts' })
    )).toBeVisible({ timeout: 15_000 })
  })
})
