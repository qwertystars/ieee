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

describe('P10: Analytics + Decision Support + Search/KB', () => {
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

  it('writes and reads analytics rollup', async () => {
    const { status: writeStatus } = await postJSON('/api/analytics/rollup', {
      metricName: 'incident_count',
      metricValue: 5,
      period: 'daily',
    }, testOrgId);
    expect(writeStatus).toBe(201);

    const { status, body } = await fetchJSON('/api/analytics/dashboard', testOrgId);
    expect(status).toBe(200);
    const data = body as { items: unknown[] };
    expect(data.items.length).toBeGreaterThan(0);
  });

  it('creates a hash-chained decision', async () => {
    const { status, body } = await postJSON('/api/decisions', {
      engine: 'evacuation',
      title: 'Evacuate Zone A',
      recommendation: 'Immediate evacuation',
      confidence: 0.85,
      citations: ['task-1', 'task-2'],
      riskScore: 0.8,
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; hash: string; status: string };
    expect(data.hash).toBeDefined();
    expect(data.status).toBe('draft');
  });

  it('approves a decision (human-only)', async () => {
    const create = await postJSON('/api/decisions', {
      engine: 'shelter',
      title: 'Open Shelter B',
    }, testOrgId);
    const id = (create.body as { id: string }).id;

    const { status, body } = await postJSON(`/api/decisions/${id}/approve`, {}, testOrgId);
    expect(status).toBe(200);
    expect((body as { status: string }).status).toBe('approved');
  });

  it('searches across entities', async () => {
    const { status, body } = await fetchJSON('/api/search?q=test', testOrgId);
    expect(status).toBe(200);
    const data = body as { items: { type: string; id: string; title: string }[] };
    expect(Array.isArray(data.items)).toBe(true);
  });

  it('saves a search', async () => {
    const { status, body } = await postJSON('/api/search/save', {
      name: 'My Search',
      query: 'flood',
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('creates and lists KB documents', async () => {
    const { status } = await postJSON('/api/kb/documents', {
      title: 'Evacuation SOP',
      contentMd: '# Evacuation SOP\n\n1. Alert\n2. Move',
      docType: 'sop',
      tags: ['evac', 'emergency'],
    }, testOrgId);
    expect(status).toBe(201);

    const { status: getStatus, body } = await fetchJSON('/api/kb/documents', testOrgId);
    expect(getStatus).toBe(200);
    expect((body as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });

  it('returns analytics summary', async () => {
    const { status, body } = await fetchJSON('/api/analytics/summary', testOrgId);
    expect(status).toBe(200);
    const data = body as { incidents: number; tasks: number; shelters: number; alerts: number };
    expect(data.incidents).toBeGreaterThanOrEqual(0);
  });
});
