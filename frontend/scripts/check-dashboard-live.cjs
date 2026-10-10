const { chromium } = require('playwright');
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const base = process.env.DASHBOARD_BASE_URL || 'http://localhost:5173';
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH, args: ['--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [], responses = [], sockets = [], checks = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/') || ['8001', '8765'].includes(url.port)) responses.push({ path: url.pathname, port: url.port, status: response.status() });
  });
  page.on('websocket', socket => { if (new URL(socket.url()).port === '8001') sockets.push(socket); });
  try {
    await page.goto(base);
    await page.getByRole('heading', { name: 'Rescue command center' }).waitFor();
    if (await page.evaluate(() => getComputedStyle(document.querySelector('#root > div')).backgroundColor !== 'rgb(2, 6, 23)')) throw new Error('Dashboard styles are missing');
    await page.evaluate(async () => {
      const cache = await caches.open('resqnet-v2-shell');
      await cache.put('/src/index.css', new Response('stale development stylesheet'));
    });
    await page.reload();
    await page.getByRole('heading', { name: 'Rescue command center' }).waitFor();
    await page.waitForFunction(async () => !(await caches.keys()).some(name => name.startsWith('resqnet-')));
    checks.push({ development_cache_cleared: true, dashboard_styles_loaded: true });
    const tabs = [
      ['Situation map', 'Rivertown Cyclone-Flood 2026'], ['Survivor map', 'Network Status'],
      ['Planning & dispatch', 'Action proposals pending review.'], ['Route sandbox', 'Route planning sandbox'],
      ['Digital twin', 'Digital-twin device simulator control.'], ['Field operations', 'Field Responder'],
      ['AI hypotheses', 'Competing explanations with confidence and evidence.'], ['Audit trail', 'Hash-chained append-only event log.'],
    ];
    for (const [name, text] of tabs) {
      await page.getByRole('button', { name, exact: true }).click();
      const workspace = page.locator('#operations-workspace');
      await workspace.getByText(text, { exact: false }).first().waitFor();
      await page.waitForTimeout(350);
      if (/Simulated Data|not for operational use/.test(await workspace.innerText())) throw new Error(`Unwanted banner: ${name}`);
      if (/Failed to load|Platform unavailable/.test(await workspace.innerText())) throw new Error(`Failed workspace: ${name}`);
      await page.setViewportSize({ width: 390, height: 844 });
      if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) throw new Error(`Mobile overflow: ${name}`);
      await page.setViewportSize({ width: 1440, height: 1100 });
      checks.push({ workspace: name, loaded: true, mobile_overflow: false });
      console.log(`Loaded: ${name}`);
    }
    await page.getByRole('button', { name: 'Audit trail', exact: true }).click();
    await page.getByRole('button', { name: 'Verify audit chain', exact: true }).click();
    await page.getByText('Chain is valid — all hashes match').waitFor();
    await page.getByRole('button', { name: 'Digital twin', exact: true }).click();
    await page.getByRole('button', { name: 'Start simulation', exact: true }).click();
    await page.getByLabel('State: running', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Select device rescue-ball-001', exact: true }).click();
    const telemetry = page.getByRole('region', { name: 'Telemetry for rescue-ball-001', exact: true });
    await telemetry.getByText('Battery', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Pause simulation', exact: true }).click();
    await page.getByLabel('State: paused', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Resume simulation', exact: true }).click();
    await page.getByLabel('State: running', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Inject fault battery_drain', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Fault battery_drain injected' }).waitFor();
    await page.getByRole('button', { name: 'Stop simulation', exact: true }).click();
    await page.getByLabel('State: stopped', { exact: true }).waitFor();
    await page.getByRole('link', { name: 'View details for rescue-ball-001', exact: true }).click();
    await page.getByRole('heading', { name: 'rescue-ball-001', exact: true }).waitFor();
    await page.getByRole('region', { name: 'Device state', exact: true }).waitFor();
    checks.push({ simulator_controls: 'start, pause, resume, inject fault, stop', telemetry: true, device_details: true });
    await page.goto(base);
    await page.getByRole('heading', { name: 'Rescue command center' }).waitFor();
    await page.screenshot({ path: '/tmp/ieee-dashboard-live.png', fullPage: true });
    if (!sockets.length) throw new Error('No live mesh WebSocket connection');
    if (!responses.some(r => r.port === '8765' && r.status === 200)) throw new Error('Thermal feed not connected');
    const failures = responses.filter(r => r.status >= 400);
    if (failures.length || errors.length) throw new Error(JSON.stringify({ failures, errors }));
    const output = path.resolve(__dirname, '../../evidence/unified-dashboard/live-browser.json');
    fs.writeFileSync(output, JSON.stringify({ status: 'PASS', created_at: new Date().toISOString(), scope: 'Real local services; no request mocks; seeded Rivertown scenario; no physical hardware', checks, responses, page_errors: errors, script_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex') }, null, 2) + '\n');
    console.log('PASS: all 8 workspaces, mobile layouts, real simulator controls/telemetry/device details, audit verification, mesh WebSocket and thermal API.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
