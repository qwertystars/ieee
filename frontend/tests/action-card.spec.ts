import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve, dirname } from 'node:path'
import { transpileModule } from 'typescript'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const componentSource = readFileSync(
  resolve(__dirname, '../src/components/ActionCard.tsx'),
  'utf-8'
)

// Transpile TypeScript → JavaScript (strips types, converts JSX to React.createElement)
// Use module: 'esnext' so imports/exports stay as ES syntax (strip-able by regex).
// 'none' emits CommonJS (exports.X / require) which breaks in the browser.
const transpiled = transpileModule(componentSource, {
  compilerOptions: { jsx: 'react', module: 'esnext', target: 'ES2020' },
})

// Strip imports/exports so the code runs as plain browser globals
const browserCode = transpiled.outputText
  .replace(/import\s+[^;]+from\s+['"][^'"]+['"];?\s*\n?/g, '')
  .replace(/export\s+default\s+\w+;?\s*\n?/g, '')
  .replace(/export\s+/g, '')
  .replace(/<\/script>/g, '<\\/script>')

const HTML = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://unpkg.com/react@18/umd/react.development.js"><\/script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"><\/script>
  <script src="https://cdn.tailwindcss.com"><\/script>
</head>
<body class="bg-gray-900 p-4">
  <div id="root"></div>
  <script>
    const { useState } = React;
    ${browserCode}

    const MOCK_ACTION = {
      id: 'action-001',
      proposedAction: 'Dispatch Boat B3',
      operationalObjective: 'Reach stranded residents',
      benefitRange: { low: 31, high: 47, unit: 'lives' },
      timeSensitivity: '22 minutes',
      resourcesRequired: ['Boat B3'],
      primaryEvidence: [
        { id: 'obs-001', label: 'Flood observation' },
        { id: 'obs-002', label: 'Stranded residents' },
      ],
      contradictingEvidence: 'traffic observation',
      assumptions: ['180m radius'],
      confidence: 0.72,
      calibration: 'Confidence 72%',
      alternatives: [{ action: 'Team R2', failureProbability: 0.3 }],
      failureContingency: 'bridge camera',
      equityImpact: 'elderly residents',
    };

    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(React.createElement(ActionCard, {
      action: MOCK_ACTION,
      onEvidenceClick: (obsId) => { window.__evidenceClicked = obsId; },
      onApprove: (id) => { window.__approveCalled = id; },
      onDismiss: (id) => { window.__dismissCalled = id; },
      onModify: (id) => { window.__modifyCalled = id; },
    }));
  <\/script>
</body>
</html>`

test.describe('ActionCard — SOTA spec §10.1', () => {
  test('renders all 13 fields', async ({ page }) => {
    await page.setContent(HTML)
    await page.waitForSelector('[data-testid="action-card"]', { timeout: 15_000 })

    // 1. Proposed action
    await expect(page.getByTestId('proposed-action')).toContainText('Dispatch Boat B3')
    // 2. Operational objective
    await expect(page.getByTestId('operational-objective')).toContainText('Reach stranded residents')
    // 3. Expected benefit range
    await expect(page.getByTestId('benefit-range')).toContainText('[31, 47]')
    // 4. Time sensitivity
    await expect(page.getByTestId('time-sensitivity')).toContainText('22 minutes')
    // 5. Resources required
    await expect(page.getByTestId('resources-required')).toContainText('Boat B3')
    // 6. Primary evidence (linked observation IDs, clickable)
    await expect(page.getByTestId('primary-evidence')).toBeVisible()
    await expect(page.getByTestId('evidence-link-obs-001')).toBeVisible()
    await expect(page.getByTestId('evidence-link-obs-002')).toBeVisible()
    // 7. Contradicting evidence
    await expect(page.getByTestId('contradicting-evidence')).toContainText('traffic observation')
    // 8. Assumptions
    await expect(page.getByTestId('assumptions')).toContainText('180m radius')
    // 9. Confidence/calibration
    await expect(page.getByTestId('confidence-value')).toContainText('72%')
    // 10. Alternative actions
    await expect(page.getByTestId('alternative-actions')).toContainText('Team R2')
    // 11. Failure contingency
    await expect(page.getByTestId('failure-contingency')).toContainText('bridge camera')
    // 12. Equity impact
    await expect(page.getByTestId('equity-impact')).toContainText('elderly residents')
    // 13. Operator controls
    await expect(page.getByTestId('approve-button')).toBeVisible()
    await expect(page.getByTestId('dismiss-button')).toBeVisible()
    await expect(page.getByTestId('modify-button')).toBeVisible()
  })

  test('evidence links are clickable and navigate to observation detail', async ({ page }) => {
    await page.setContent(HTML)
    await page.waitForSelector('[data-testid="action-card"]', { timeout: 15_000 })

    await page.getByTestId('evidence-link-obs-001').click()

    const clicked = await page.evaluate(() => (window as any).__evidenceClicked)
    expect(clicked).toBe('obs-001')
  })

  test('uncertainty range displayed as [low, high]', async ({ page }) => {
    await page.setContent(HTML)
    await page.waitForSelector('[data-testid="action-card"]', { timeout: 15_000 })

    const range = await page.getByTestId('benefit-range').textContent()
    expect(range).toMatch(/\[31,\s*47\]/)
  })

  test('approve button calls API and updates status', async ({ page }) => {
    await page.route('**/api/actions/**', route =>
      route.fulfill({ status: 200, body: JSON.stringify({ ok: true }) })
    )

    await page.setContent(HTML)
    await page.waitForSelector('[data-testid="action-card"]', { timeout: 15_000 })

    await page.getByTestId('approve-button').click()

    await expect(page.getByTestId('action-card')).toHaveAttribute('data-status', 'approved')
    const called = await page.evaluate(() => (window as any).__approveCalled)
    expect(called).toBe('action-001')
  })

  test('dismiss button calls API and updates status', async ({ page }) => {
    await page.route('**/api/actions/**', route =>
      route.fulfill({ status: 200, body: JSON.stringify({ ok: true }) })
    )

    await page.setContent(HTML)
    await page.waitForSelector('[data-testid="action-card"]', { timeout: 15_000 })

    await page.getByTestId('dismiss-button').click()

    await expect(page.getByTestId('action-card')).toHaveAttribute('data-status', 'dismissed')
    const called = await page.evaluate(() => (window as any).__dismissCalled)
    expect(called).toBe('action-001')
  })
})
