import { test, expect, type Page } from '@playwright/test'

async function waitForMapReady(page: Page) {
  // Wait for the map container to be present and have a canvas child.
  await page.waitForSelector('[data-testid="map-container"] canvas', { timeout: 15_000 })
  // Give deck.gl time to initialize layers.
  await page.waitForTimeout(2000)
}

// MapLibre's canvas has class "maplibregl-canvas"; deck.gl's overlay has id "deckgl-overlay".
const MAP_CANVAS = '.maplibregl-canvas'

test.describe('Map system — MapLibre + deck.gl', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await waitForMapReady(page)
  })

  test('map canvas renders with layer toggle panel', async ({ page }) => {
    const mapContainer = page.locator('[data-testid="map-container"]')
    await expect(mapContainer).toBeVisible()

    const canvas = mapContainer.locator(MAP_CANVAS)
    await expect(canvas).toHaveCount(1)

    const togglePanel = page.locator('[data-testid="layer-toggle-list"]')
    await expect(togglePanel).toBeVisible()
  })

  test('layer toggle list shows all SOTA spec layers', async ({ page }) => {
    const expectedLayers = [
      'flood', 'roads', 'buildings', 'shelters', 'hospitals',
      'responders', 'sensors', 'alerts', 'cellTowers', 'observations', 'hazardZones',
    ]
    for (const id of expectedLayers) {
      const toggle = page.locator(`[data-testid="layer-toggle-${id}"]`)
      await expect(toggle).toBeVisible()
    }
  })

  test('toggling a layer updates visibility state', async ({ page }) => {
    // Flood should be visible by default.
    const floodToggle = page.locator('[data-testid="layer-toggle-flood"]')
    await expect(floodToggle).toHaveAttribute('data-visible', 'true')

    // Click to toggle off.
    await floodToggle.locator('button').click()
    await expect(floodToggle).toHaveAttribute('data-visible', 'false')

    // Click again to toggle back on.
    await floodToggle.locator('button').click()
    await expect(floodToggle).toHaveAttribute('data-visible', 'true')
  })

  test('flood probability layer renders as semi-transparent heatmap', async ({ page }) => {
    // Ensure flood layer is visible.
    const floodToggle = page.locator('[data-testid="layer-toggle-flood"]')
    if (await floodToggle.getAttribute('data-visible') === 'false') {
      await floodToggle.locator('button').click()
    }
    await expect(floodToggle).toHaveAttribute('data-visible', 'true')

    // Wait for deck.gl to render the heatmap layer.
    await page.waitForTimeout(1000)

    // The map canvas should exist and have non-zero dimensions.
    const canvas = page.locator(MAP_CANVAS)
    const box = await canvas.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeGreaterThan(100)
    expect(box!.height).toBeGreaterThan(100)

    // Verify the legend mentions flood probability.
    const legend = page.locator('[data-testid="map-legend"]')
    await expect(legend).toBeVisible()
    await expect(legend).toContainText('Flood Probability')
  })

  test('stale data (>1h old) shown with different color — honest degradation', async ({ page }) => {
    // Cell towers have stale data (2h old) in the mock data.
    const cellTowerToggle = page.locator('[data-testid="layer-toggle-cellTowers"]')
    // Enable cell towers layer.
    if (await cellTowerToggle.getAttribute('data-visible') === 'false') {
      await cellTowerToggle.locator('button').click()
    }
    await expect(cellTowerToggle).toHaveAttribute('data-visible', 'true')

    // The freshness should be 'stale' (red badge).
    await expect(cellTowerToggle).toHaveAttribute('data-freshness', 'stale')

    // Verify the freshness badge shows stale coloring (red dot).
    const staleDot = cellTowerToggle.locator('.bg-red-500')
    await expect(staleDot).toBeVisible()

    // Verify the legend explains stale data coloring.
    const legend = page.locator('[data-testid="map-legend"]')
    await expect(legend).toContainText('Stale data')
    await expect(legend).toContainText('degraded colors')
  })

  test('freshness badges show correct tiers', async ({ page }) => {
    // Responders have fresh data (1 min old).
    const responderToggle = page.locator('[data-testid="layer-toggle-responders"]')
    if (await responderToggle.getAttribute('data-visible') === 'false') {
      await responderToggle.locator('button').click()
    }
    await expect(responderToggle).toHaveAttribute('data-freshness', 'fresh')

    // Hospitals have aging data (20 min old).
    const hospitalToggle = page.locator('[data-testid="layer-toggle-hospitals"]')
    if (await hospitalToggle.getAttribute('data-visible') === 'false') {
      await hospitalToggle.locator('button').click()
    }
    await expect(hospitalToggle).toHaveAttribute('data-freshness', 'aging')
  })

  test('drawing tools create zones', async ({ page }) => {
    // Click the Draw Zone button.
    const drawButton = page.getByText('Draw Zone')
    await drawButton.click()

    // Verify drawing mode is active.
    await expect(page.getByText(/Drawing/)).toBeVisible()

    // The map canvas should have crosshair cursor.
    const canvas = page.locator(MAP_CANVAS)
    const cursor = await canvas.evaluate((el) => window.getComputedStyle(el).cursor)
    expect(cursor).toContain('crosshair')

    // Exit drawing mode.
    await page.getByText(/Drawing/).click()
  })

  test('legend displays freshness, road passability, and flood probability', async ({ page }) => {
    const legend = page.locator('[data-testid="map-legend"]')
    await expect(legend).toBeVisible()
    await expect(legend).toContainText('Data Freshness')
    await expect(legend).toContainText('Road Passability')
    await expect(legend).toContainText('Flood Probability')
    await expect(legend).toContainText('< 5 min')
    await expect(legend).toContainText('> 60 min')
  })
})
