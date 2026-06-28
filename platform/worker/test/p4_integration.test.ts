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

async function fetchJSON(path: string, init?: RequestInit): Promise<{ status: number; body: unknown }> {
  await ensureMigrations();
  const resp = await SELF.fetch(`https://test.local${path}`, init);
  const text = await resp.text(); let body: unknown; try { body = JSON.parse(text); } catch { body = text; }
  return { status: resp.status, body };
}

async function postJSON(path: string, data: unknown, orgId?: string): Promise<{ status: number; body: unknown }> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (orgId) headers['X-Org-Id'] = orgId;
  return fetchJSON(path, { method: 'POST', headers, body: JSON.stringify(data) });
}

describe('P4: Shelter Management + Missing Persons', () => {
  let testOrgId: string;

  beforeAll(async () => {
    await ensureMigrations();
    const { body } = await postJSON('/api/seed/demo', {});
    testOrgId = (body as { orgId: string }).orgId;
  });

  it('creates a missing person report', async () => {
    const { status, body } = await postJSON('/api/missing-persons', {
      incidentId: 'test-incident',
      fullName: 'Jane Doe',
      ageGroup: 'adult',
      sex: 'female',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; pfifId: string; ok: boolean };
    expect(data.id).toBeDefined();
    expect(data.pfifId).toMatch(/^PFIF-/);
    expect(data.ok).toBe(true);
  });

  it('lists missing persons', async () => {
    const resp = await SELF.fetch(`https://test.local/api/missing-persons?incidentId=test-incident`, {
      headers: { 'X-Org-Id': testOrgId },
    });
    expect(resp.status).toBe(200);
    const data = await resp.json() as { items: unknown[] };
    expect(data.items.length).toBeGreaterThanOrEqual(1);
  });

  it('creates a found person and auto-suggests match', async () => {
    const { status, body } = await postJSON('/api/found-persons', {
      incidentId: 'test-incident',
      fullName: 'Jane Doe',
      ageGroup: 'adult',
      sex: 'female',
      source: 'shelter',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; suggestions: { missingId: string; score: number }[] };
    expect(data.id).toBeDefined();
    expect(data.suggestions.length).toBeGreaterThan(0);
    expect(data.suggestions[0]!.score).toBeGreaterThan(0.6);
  });

  it('finds nearest shelters', async () => {
    const resp = await SELF.fetch(`https://test.local/api/shelters/nearest?lat=40.7&lng=-74.0`, {
      headers: { 'X-Org-Id': testOrgId },
    });
    expect(resp.status).toBe(200);
    const data = await resp.json() as { items: { distanceKm: number }[] };
    expect(data.items).toBeDefined();
    expect(Array.isArray(data.items)).toBe(true);
  });

  it('exports PFIF', async () => {
    const resp = await SELF.fetch(`https://test.local/api/pfif/export`, {
      headers: { 'X-Org-Id': testOrgId },
    });
    expect(resp.status).toBe(200);
    const data = await resp.json() as { pfif_version: string; persons: unknown[] };
    expect(data.pfif_version).toBe('1.4');
    expect(data.persons.length).toBeGreaterThan(0);
  });

  it('creates a shelter plan', async () => {
    const { status, body } = await postJSON('/api/shelter-plans', {
      incidentId: 'test-incident',
      planType: 'mega',
      name: 'Mega Shelter Plan',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });
});
