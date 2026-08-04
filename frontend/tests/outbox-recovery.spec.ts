import { test, expect, type Page } from '@playwright/test'

async function login(page: Page) {
  const response = await page.request.post(`${process.env.BACKEND_URL ?? 'http://localhost:8000'}/api/auth/login`, { form: { username: 'admin@demo.disaster', password: 'demo1234' } })
  expect(response.ok()).toBeTruthy()
  const token = (await response.json() as { access_token: string }).access_token
  await page.goto('/login')
  await page.evaluate(value => localStorage.setItem('resqnet.jwt', value), token)
  await page.reload()
  await page.goto('/dashboard')
  await page.waitForURL('**/dashboard', { timeout: 15_000 })
}

test.describe('durable outbox recovery', () => {
  test('crash and network recovery leaves no orphan sending item', async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: 'Field' }).click()
    await page.waitForURL('**/field', { timeout: 10_000 })
    const taskSelect = page.locator('select[aria-label^="Update status for task"]').first()
    await expect(taskSelect).toBeVisible({ timeout: 15_000 })

    await page.context().setOffline(true)
    const nextStatus = (await taskSelect.inputValue()) === 'completed' ? 'blocked' : 'completed'
    await taskSelect.selectOption(nextStatus)
    await expect(page.locator('[data-testid="pending-badge"]')).toBeVisible({ timeout: 10_000 })

    await page.context().setOffline(false)
    await page.route('**/api/tasks/**', async route => {
      if (route.request().method() === 'PATCH') await route.abort('failed')
      else await route.continue()
    })
    await page.reload()
    await expect(page.locator('[data-testid="pending-badge"]')).toBeVisible({ timeout: 10_000 })
    await page.unroute('**/api/tasks/**')
    await page.context().setOffline(true)
    await page.context().setOffline(false)
    await expect(page.locator('[data-testid="synced-badge"]')).toBeVisible({ timeout: 30_000 })
  })

  test('network cache excludes authenticated API responses', async ({ page }) => {
    await login(page)
    await page.waitForTimeout(500)
    const cachedApiUrls = await page.evaluate(async () => {
      const names = await caches.keys()
      const requests = (await Promise.all(names.map(async name => (await caches.open(name)).keys()))).flat()
      return requests.filter(request => new URL(request.url).pathname.startsWith('/api/')).map(request => request.url)
    })
    expect(cachedApiUrls).toEqual([])
  })

  test('409 task update exposes manual conflict resolution instead of success', async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: 'Field' }).click()
    await page.waitForURL('**/field', { timeout: 10_000 })
    const taskSelect = page.locator('select[aria-label^="Update status for task"]').first()
    await expect(taskSelect).toBeVisible({ timeout: 15_000 })

    await page.context().setOffline(true)
    const nextStatus = (await taskSelect.inputValue()) === 'completed' ? 'blocked' : 'completed'
    await taskSelect.selectOption(nextStatus)
    await expect(page.locator('[data-testid="pending-badge"]')).toBeVisible({ timeout: 10_000 })

    await page.route('**/api/tasks/**', async route => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Authoritative task state changed' }) })
      } else {
        await route.continue()
      }
    })
    await page.context().setOffline(false)
    await expect(page.locator('[data-testid="conflict-badge"]')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('[data-testid="conflict-badge"]')).toContainText('manual resolution required')
    await expect(page.locator('[data-testid="synced-badge"]')).not.toBeVisible()
  })
})
