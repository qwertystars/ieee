import { describe, it, expect, beforeAll } from 'vitest';
import { env, SELF } from 'cloudflare:test';

declare module 'cloudflare:test' {
  interface ProvidedEnv extends Env {}
}

let migrationsRun = false;

async function ensureMigrations() {
  if (migrationsRun) return;
  if (!env.__MIGRATION_SQL) return;
  const sqlStatements = JSON.parse(env.__MIGRATION_SQL) as string[];
  for (const stmt of sqlStatements) { try { await env.db.prepare(stmt).run(); } catch { /* */ } }
  migrationsRun = true;
}

async function fetchJSON(path: string, orgId?: string, init?: RequestInit): Promise<{ status: number; body: unknown }> {
  await ensureMigrations();
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string> ?? {}) };
  if (orgId) headers['X-Org-Id'] = orgId;
  const resp = await SELF.fetch(`https://test.local${path}`, { ...init, headers });
  const text = await resp.text(); let body: unknown; try { body = JSON.parse(text); } catch { body = text; }
  return { status: resp.status, body };
}

async function postJSON(path: string, data: unknown, orgId?: string): Promise<{ status: number; body: unknown }> {
  return fetchJSON(path, orgId, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

describe('P13+P14: Observability + Sci-Fi', () => {
  let testOrgId: string;

  beforeAll(async () => {
    await ensureMigrations();
    const { body } = await postJSON('/api/seed/demo', {});
    const seedBody = body as { orgId?: string };
    if (seedBody.orgId) { testOrgId = seedBody.orgId; } else {
      const result = await env.db.prepare('SELECT id FROM orgs WHERE slug = ?').bind('rivertown-demo').first<{ id: string }>();
      testOrgId = result?.id ?? 'system';
    }
  });

  // P13
  it('records SLO metrics and reads dashboard', async () => {
    const { status } = await postJSON('/api/slo/metrics', {
      metricName: 'api_latency',
      p95: 120,
      errorRate: 0.02,
      requestCount: 1000,
    }, testOrgId);
    expect(status).toBe(201);

    const dash = await fetchJSON('/api/slo/dashboard', testOrgId);
    expect(dash.status).toBe(200);
    expect((dash.body as { avgP95: number }).avgP95).toBeGreaterThanOrEqual(0);
  });

  it('registers and lists cron jobs', async () => {
    const { status } = await postJSON('/api/cron/jobs', {
      name: 'nightly_backup',
      schedule: '0 2 * * *',
    }, testOrgId);
    expect(status).toBe(201);

    const list = await fetchJSON('/api/cron/jobs', testOrgId);
    expect(list.status).toBe(200);
    expect((list.body as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });

  it('creates locale documents and glossary terms', async () => {
    const locale = await postJSON('/api/i18n/locales', {
      locale: 'es',
      namespace: 'common',
      content: { hello: 'hola' },
    }, testOrgId);
    expect(locale.status).toBe(201);

    const getLocale = await fetchJSON('/api/i18n/locales/es', testOrgId);
    expect(getLocale.status).toBe(200);

    const glossary = await postJSON('/api/i18n/glossary', {
      term: 'evacuate',
      translations: { es: 'evacuar', fr: ' évacuer' },
      locked: true,
    }, testOrgId);
    expect(glossary.status).toBe(201);
  });

  // P14
  it('creates a digital twin output', async () => {
    const { status, body } = await postJSON('/api/scifi/digital-twin', {
      incidentId: 'test-incident',
      layers: { overlays: ['weather', 'shelters', 'hazards'] },
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { reviewStatus: string }).reviewStatus).toBe('draft');
  });

  it('generates an AI response plan', async () => {
    const { status, body } = await postJSON('/api/scifi/ai-plan', {
      incidentId: 'test-incident',
      plan: { phases: ['alert', 'evacuate', 'shelter'], objectives: ['save lives'] },
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { reviewStatus: string }).reviewStatus).toBe('draft');
  });

  it('computes hyperlocal risk scores', async () => {
    const { status, body } = await postJSON('/api/scifi/hyperlocal', {
      incidentId: 'test-incident',
      h3Cells: ['cell-1', 'cell-2', 'cell-3'],
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { scores: { h3: string; riskScore: number }[] };
    expect(data.scores.length).toBe(3);
    data.scores.forEach((s) => { expect(s.riskScore).toBeGreaterThan(0); expect(s.riskScore).toBeLessThan(1); });
  });

  it('plans drone swarm routes', async () => {
    const { status, body } = await postJSON('/api/scifi/drone-swarm', {
      area: { lat: 40.7, lng: -74.0, w: 0.1, h: 0.1 },
      droneCount: 4,
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { waypoints: { drone: number }[]; droneCount: number };
    expect(data.droneCount).toBe(4);
    expect(data.waypoints.length).toBe(4);
  });

  it('generates auto briefing', async () => {
    const { status, body } = await postJSON('/api/scifi/auto-briefing', {
      horizon: '6h',
      incidentId: 'test-incident',
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { horizon: string }).horizon).toBe('6h');
  });

  it('creates a contradiction detection output', async () => {
    const { status, body } = await postJSON('/api/scifi/contradiction_detect', {
      incidentId: 'test-incident',
      output: { contradictions: [] },
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { reviewStatus: string }).reviewStatus).toBe('draft');
  });
});
