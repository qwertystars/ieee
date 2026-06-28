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
  for (const stmt of sqlStatements) {
    try { await env.db.prepare(stmt).run(); } catch { /* tables may already exist */ }
  }
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

describe('P5: Data Ingestion + Weather + Population Impact', () => {
  let testOrgId: string;

  beforeAll(async () => {
    await ensureMigrations();
    const { body } = await postJSON('/api/seed/demo', {});
    const seedBody = body as { orgId?: string };
    if (seedBody.orgId) {
      testOrgId = seedBody.orgId;
    } else {
      const result = await env.db.prepare('SELECT id FROM orgs WHERE slug = ?').bind('rivertown-demo').first<{ id: string }>();
      testOrgId = result?.id ?? 'system';
    }
  });

  it('ingests a raw report (idempotent)', async () => {
    const { status, body } = await postJSON('/api/ingest', {
      source: 'test-feed',
      externalId: 'ext-001',
      payload: { temp: 25, rain: 10 },
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.id).toBeDefined();

    // Duplicate = no-op
    const dup = await postJSON('/api/ingest', {
      source: 'test-feed',
      externalId: 'ext-001',
      payload: { temp: 26 },
    }, testOrgId);
    expect(dup.status).toBe(200);
    expect((dup.body as { duplicate: boolean }).duplicate).toBe(true);
  });

  it('rejects webhook without HMAC signature', async () => {
    const { status } = await postJSON('/api/ingest/webhook', { data: 'test' }, testOrgId);
    expect(status).toBe(401);
  });

  it('ingests CSV upload', async () => {
    const csv = 'source,external_id,temp\nfeed-1,ext-a,25\nfeed-1,ext-b,26\n';
    const resp = await SELF.fetch('https://test.local/api/ingest/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv', 'X-Org-Id': testOrgId },
      body: csv,
    });
    expect(resp.status).toBe(201);
    const data = await resp.json() as { inserted: number; quarantined: number };
    expect(data.inserted).toBe(2);
    expect(data.quarantined).toBe(0);
  });

  it('records weather observation', async () => {
    const { status, body } = await postJSON('/api/weather/obs', {
      incidentId: 'test-incident',
      tempC: 32,
      humidity: 80,
      rainMm: 15,
      windSpeedKmh: 20,
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });

  it('computes weather risk indices', async () => {
    const { status, body } = await postJSON('/api/weather/test-incident/indices', {}, testOrgId);
    expect(status).toBe(200);
    const data = body as { fwi: number; floodRisk: number; heatwaveRisk: number; opRiskScore: number };
    expect(data.fwi).toBeGreaterThanOrEqual(0);
    expect(data.floodRisk).toBeGreaterThanOrEqual(0);
    expect(data.opRiskScore).toBeGreaterThanOrEqual(0);
  });

  it('preloads pop_h3 and estimates affected population', async () => {
    const cells = [
      { h3: '89283082803ffff', pop: 500 },
      { h3: '8928308280bffff', pop: 300 },
      { h3: '89283082807ffff', pop: 200 },
    ];
    const preload = await postJSON('/api/pop/preload', { cells }, testOrgId);
    expect(preload.status).toBe(201);
    expect((preload.body as { inserted: number }).inserted).toBe(3);

    const { status, body } = await postJSON('/api/pop/estimate', {
      incidentId: 'test-incident',
      h3Cells: cells.map((c) => c.h3),
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { totalAffected: number; elderly: number; children: number; waterLitersNeeded?: number };
    expect(data.totalAffected).toBe(1000);
    expect(data.elderly).toBe(150);
    expect(data.children).toBe(250);
  });

  it('rejects AOI exceeding 50,000 H3 cells', async () => {
    const bigCells = Array.from({ length: 50001 }, (_, i) => `cell-${i}`);
    const { status, body } = await postJSON('/api/pop/estimate', {
      incidentId: 'test-incident',
      h3Cells: bigCells,
    }, testOrgId);
    expect(status).toBe(413);
    const data = body as { error: { code: string } };
    expect(data.error.code).toBe('AOI_TOO_LARGE');
  });

  it('estimates needs using Sphere standards', async () => {
    const { status, body } = await postJSON('/api/pop/needs', {
      incidentId: 'test-incident',
      totalAffected: 1000,
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { evacNeeded: number; shelterNeeded: number; waterLitersNeeded: number; foodNeeded: number };
    expect(data.evacNeeded).toBe(300);
    expect(data.shelterNeeded).toBe(180);
    expect(data.waterLitersNeeded).toBe(15000);
    expect(data.foodNeeded).toBe(1000);
  });

  it('registers a feed source', async () => {
    const { status, body } = await postJSON('/api/feeds', {
      name: 'Open-Meteo',
      kind: 'weather',
      url: 'https://api.open-meteo.com/v1/forecast',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });
});
