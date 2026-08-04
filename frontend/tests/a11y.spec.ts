import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const OPERATIONAL_PROXY = `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Responder workflow proxy</title></head>
  <body>
    <main aria-labelledby="workflow-title">
      <h1 id="workflow-title">Responder workflow scripted proxy</h1>
      <section aria-labelledby="decision-title">
        <h2 id="decision-title">Review recommendation</h2>
        <p id="rationale-help">Record the operational rationale before approval.</p>
        <label for="rationale">Approval rationale</label>
        <textarea id="rationale" aria-describedby="rationale-help">Verified against current observations</textarea>
        <button type="button" aria-label="Approve action: Dispatch rescue boat">Approve</button>
        <button type="button" aria-label="Dismiss action: Dispatch rescue boat">Dismiss</button>
        <button type="button" aria-label="Modify action: Dispatch rescue boat">Modify</button>
        <button type="button" aria-label="Request dispatch: Dispatch rescue boat">Request Dispatch</button>
      </section>
      <section aria-label="Operational degradation states">
        <p role="status" aria-live="polite">Data may be stale. Last updated 2 minutes ago.</p>
        <p role="status" aria-live="assertive">You are offline. Changes are queued for sync.</p>
        <p role="status" aria-live="assertive">Conflict requires manual resolution. No last-write-wins action was taken.</p>
        <p role="alert" aria-live="assertive">The request failed. Retry is available.</p>
      </section>
    </main>
  </body>
</html>`

test.describe('Task 22 accessibility scripted proxies', () => {
  test('keyboard reaches critical responder controls and states have accessible names', async ({ page }) => {
    await page.setContent(OPERATIONAL_PROXY)

    const controls = page.getByRole('button')
    await expect(controls).toHaveCount(4)
    for (const name of ['Approve', 'Dismiss', 'Modify', 'Request Dispatch']) {
      const control = page.getByRole('button', { name: new RegExp(name, 'i') })
      await control.focus()
      await expect(control).toBeFocused()
    }

    await expect(page.getByLabel('Approval rationale')).toBeVisible()
    await expect(page.locator('[role="status"]').filter({ hasText: /stale/i })).toBeVisible()
    await expect(page.locator('[role="status"]').filter({ hasText: /offline/i })).toBeVisible()
    await expect(page.locator('[role="status"]').filter({ hasText: /conflict/i })).toBeVisible()
    await expect(page.locator('[role="alert"]').filter({ hasText: /failed/i })).toBeVisible()
  })

  test('rendered responder proxy has no axe violations', async ({ page }) => {
    await page.setContent(OPERATIONAL_PROXY)
    const results = await new AxeBuilder({ page }).analyze()
    expect(results.violations).toEqual([])
  })

  test('long localized control labels preserve keyboard reachability', async ({ page }) => {
    await page.setContent(OPERATIONAL_PROXY)
    const localizedLabel = 'Aprobar accion: evacuar residentes del sector norte antes del cierre de la carretera'
    await page.getByRole('button', { name: /Approve action/i }).evaluate((element, label) => {
      element.setAttribute('aria-label', label)
    }, localizedLabel)
    const localizedControl = page.getByRole('button', { name: localizedLabel })
    await localizedControl.focus()
    await expect(localizedControl).toBeFocused()
  })
})
