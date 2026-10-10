const { chromium } = require('playwright');
const base = process.env.DASHBOARD_BASE_URL || 'http://localhost:5173';
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH });
  const preview = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const previewRequests = [];
  preview.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/') || ['8001', '8765'].includes(url.port) || url.hostname === '192.168.4.1') previewRequests.push(request.url());
  });
  preview.on('websocket', socket => { if (new URL(socket.url()).port !== new URL(base).port) previewRequests.push(socket.url()); });
  await preview.route('**:8765/**', route => route.fulfill({ json: [] }));
  await preview.route('**:8001/health', route => route.fulfill({ json: { status: 'ok' } }));
  await preview.routeWebSocket('**:8001/ws/route', ws => {
    previewRequests.push('ws://localhost:8001/ws/route');
    ws.send(JSON.stringify({ path: [], survivors: [], blocked_edges: [] }));
  });
  await preview.route('http://localhost:8000/**', route => route.fulfill({ status: 503, json: { detail: 'Test outage' } }));
  await preview.goto(`${base}/preview`);
  await preview.getByRole('heading', { name: 'Rescue command center' }).waitFor();
  await preview.getByText('Connected; waiting for thermal detections.').waitFor();
  if (await preview.getByText('Offline preview', { exact: false }).count()) throw new Error('Main dashboard still uses sample preview');
  await preview.getByRole('button', { name: 'Route sandbox', exact: true }).click();
  await preview.getByRole('button', { name: 'Calculate demo path' }).click();
  await preview.getByText('Draft path: 28 grid steps; 0 blocked cells.').waitFor();
  await preview.screenshot({ path: '/tmp/ieee-dashboard-preview.png', fullPage: true });
  await preview.setViewportSize({ width: 390, height: 844 });
  if (await preview.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) throw new Error('Preview mobile overflow');
  if (!previewRequests.some(url => url.includes(':8765'))) throw new Error('Dashboard did not request the thermal feed');
  if (!previewRequests.some(url => url.includes(':8001/ws/route'))) throw new Error('Dashboard did not connect to the mesh feed');
  for (const path of ['/', '/login', '/dashboard']) {
    await preview.goto(`${base}${path}`);
    await preview.getByRole('heading', { name: 'Rescue command center' }).waitFor();
    if (await preview.getByRole('button', { name: 'Sign in', exact: true }).count()) throw new Error('Login page still shown');
  }
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  let role = 'admin';
  let failPlatform = false;
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem('resqnet.jwt', 'browser-test-only'));
  await page.route('http://localhost:8000/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (failPlatform && path === '/api/incidents') return route.fulfill({ status: 503, json: { detail: 'Test outage' } });
    const data = path.endsWith('/me')
      ? { id: 'test-user', email: 'browser-test@example.test', role, org_id: 'test' }
      : { incidents: [], count: 0 };
    return route.fulfill({ json: data });
  });
  await page.route('**:8765/**', route => route.fulfill({ json: [{ id: 1, timestamp: Date.now() / 1000, coords: [0.25, 0.5], confidence: 0.9, radius: 5 }] }));
  await page.route('**:8001/health', route => route.fulfill({ json: { status: 'ok' } }));
  await page.routeWebSocket('**:8001/ws/route', ws => ws.send(JSON.stringify({
    path: [{ x: 0, y: 0 }, { x: 20, y: 10 }],
    survivors: [{ id: 'TEST-1', x: 20, y: 10, urgency: 'medium', relay_node_id: 'R-1' }],
    blocked_edges: [],
  })));
  await page.goto(`${base}/dashboard`);
  await page.getByRole('heading', { name: 'Rescue command center' }).waitFor();
  await page.getByText('Beacon TEST-1 · relay R-1', { exact: true }).waitFor();
  await page.getByText('Candidate #1', { exact: false }).waitFor();
  await page.getByText('No active incidents', { exact: true }).waitFor();
  await page.screenshot({ path: '/tmp/ieee-dashboard-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: '/tmp/ieee-dashboard-mobile.png', fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (overflow) throw new Error('Mobile horizontal overflow');
  await page.getByRole('button', { name: 'Route sandbox', exact: true }).click();
  await page.getByRole('button', { name: 'Calculate demo path' }).click();
  await page.getByText('Draft path: 28 grid steps; 0 blocked cells.').waitFor();
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) throw new Error('Route sandbox mobile overflow');
  failPlatform = true;
  await page.route('**:8765/**', route => route.fulfill({ status: 503, json: { detail: 'Test outage' } }));
  await page.reload();
  await page.getByText('Platform unavailable').waitFor();
  await page.getByText('Thermal feed unavailable. No live detections available.').waitFor();
  await page.getByText('Beacon TEST-1 · relay R-1').waitFor();
  role = 'viewer';
  failPlatform = false;
  await page.goto(`${base}/rescue`);
  await page.waitForURL('**/dashboard');
  await page.getByText('Detailed survivor, thermal and drone feeds are available to operational roles.').waitFor();
  if (await page.getByRole('heading', { name: 'Drone flight controls' }).count()) throw new Error('Viewer can access drone panel');
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('PASS: dashboard opens without login and connects to field endpoints; no sample preview is shown; simulated field feeds render; route sandbox works; mobile has no horizontal overflow; outages stay visible; viewer rescue access is blocked.');
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
