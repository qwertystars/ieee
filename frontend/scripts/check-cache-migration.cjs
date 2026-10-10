const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const base = process.env.DASHBOARD_BASE_URL || 'http://localhost:5173';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(`${base}/dashboard`);
    await page.getByRole('heading', { name: 'Rescue command center' }).waitFor();
    const oldWorker = execFileSync('git', ['show', 'd8d12f5:frontend/public/sw.js'], {
      cwd: path.resolve(__dirname, '../..'), encoding: 'utf8',
    });
    // Install the actual earlier worker; API and application requests stay live.
    await context.route('**/sw.js', route => route.fulfill({ contentType: 'application/javascript', body: oldWorker }));
    await page.evaluate(async () => {
      await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;
    });
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await page.evaluate(async () => {
      const cache = await caches.open('resqnet-v2-shell');
      await cache.put('/src/index.css', new Response('export default ""', {
        headers: { 'Content-Type': 'application/javascript' },
      }));
    });
    await page.reload();
    await page.waitForFunction(() => !navigator.serviceWorker.controller &&
      getComputedStyle(document.querySelector('#root > div')).backgroundColor === 'rgb(2, 6, 23)');
    await page.getByRole('button', { name: 'Digital twin', exact: true }).click();
    await page.getByRole('heading', { name: 'Simulation', exact: true }).waitFor();
    if (await page.getByRole('banner', { name: 'Simulated data banner' }).count()) throw Error('Old banner present');
    console.log('PASS: earlier service worker with stale CSS is removed; dashboard styles recover; simulation banner absent.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
