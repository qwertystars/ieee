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

describe('P8: Evacuation + Medical + Logistics + Infrastructure', () => {
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

  it('routes via Dijkstra on small graph', async () => {
    const edges = [
      { fromNode: 'A', toNode: 'B', length: 5 },
      { fromNode: 'B', toNode: 'C', length: 3 },
      { fromNode: 'A', toNode: 'C', length: 10 },
    ];
    for (const e of edges) {
      await postJSON('/api/routing/edge', { ...e, regionId: 'test-region' }, testOrgId);
    }
    const { status, body } = await postJSON('/api/routing/route', { regionId: 'test-region', fromNode: 'A', toNode: 'C' }, testOrgId);
    expect(status).toBe(200);
    const data = body as { path: string[]; distance: number };
    expect(data.path).toEqual(['A', 'B', 'C']);
    expect(data.distance).toBe(8);
  });

  it('creates an evacuation zone', async () => {
    const { status, body } = await postJSON('/api/evac-zones', {
      incidentId: 'test-incident',
      zoneName: 'Zone A',
      geometry: '{"type":"Polygon","coordinates":[[[0,0],[0,1],[1,1],[1,0],[0,0]]]}',
      status: 'ordered',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });

  it('registers a medical facility', async () => {
    const { status, body } = await postJSON('/api/medical/facilities', {
      name: 'General Hospital',
      type: 'hospital',
      totalBeds: 100,
      availableBeds: 50,
      icuBeds: 10,
      erBeds: 20,
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });

  it('creates a triage patient', async () => {
    const { status, body } = await postJSON('/api/medical/triage', {
      incidentId: 'test-incident',
      triageCategory: 'immediate',
      severity: 'critical',
      name: 'John Doe',
      mciMode: true,
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });

  it('records a logistics movement (idempotent)', async () => {
    const { status, body } = await postJSON('/api/logistics/movements', {
      itemId: 'item-1',
      toLocation: 'warehouse-1',
      qty: 100,
      movementType: 'receive',
      idempotencyKey: 'idem-001',
    }, testOrgId);
    expect(status).toBe(201);

    const dup = await postJSON('/api/logistics/movements', {
      itemId: 'item-1',
      toLocation: 'warehouse-1',
      qty: 100,
      movementType: 'receive',
      idempotencyKey: 'idem-001',
    }, testOrgId);
    expect(dup.status).toBe(200);
    expect((dup.body as { duplicate: boolean }).duplicate).toBe(true);
  });

  it('creates and approves a resource request', async () => {
    const create = await postJSON('/api/resource-requests', {
      incidentId: 'test-incident',
      itemType: 'water',
      quantity: 500,
      urgency: 'high',
    }, testOrgId);
    const id = (create.body as { id: string }).id;

    const { status, body } = await postJSON(`/api/resource-requests/${id}/approve`, {}, testOrgId);
    expect(status).toBe(200);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('registers infra assets and runs BFS cascade', async () => {
    const power = await postJSON('/api/infra/assets', { name: 'Power Plant', type: 'power', status: 'operational' }, testOrgId);
    const powerId = (power.body as { id: string }).id;

    const water = await postJSON('/api/infra/assets', { name: 'Water Pump', type: 'water', parentId: powerId, status: 'operational' }, testOrgId);
    const waterId = (water.body as { id: string }).id;

    const hospital = await postJSON('/api/infra/assets', { name: 'Hospital HVAC', type: 'hospital', parentId: waterId, status: 'operational' }, testOrgId);

    const { status, body } = await postJSON(`/api/infra/${powerId}/cascade`, {}, testOrgId);
    expect(status).toBe(200);
    const data = body as { affected: string[]; count: number };
    expect(data.count).toBeGreaterThanOrEqual(1);
  });
});
