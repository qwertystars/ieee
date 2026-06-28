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

describe('P12: Multi-Agency + Drills + Early Warning + Recovery + Finance', () => {
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

  it('registers an agency', async () => {
    const { status, body } = await postJSON('/api/agencies', {
      name: 'Red Cross Local',
      capabilities: ['shelter', 'medical'],
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('creates an MOU', async () => {
    const { status, body } = await postJSON('/api/mous', {
      agencyId: 'agency-1',
      scope: 'mutual_aid',
      expiry: Date.now() + 365 * 24 * 3600 * 1000,
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('shares an incident with another org', async () => {
    const { status, body } = await postJSON('/api/incident-shares', {
      incidentId: 'test-incident',
      targetOrgId: 'org-other',
      scope: ['read'],
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('creates an exercise (drill)', async () => {
    const { status, body } = await postJSON('/api/exercises', {
      name: 'Flood Drill 2024',
      exerciseMode: 'tabletop',
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('creates a watch', async () => {
    const { status, body } = await postJSON('/api/watches', {
      hazard: 'flood',
      state: 'advisory',
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('creates a recovery case', async () => {
    const { status, body } = await postJSON('/api/recovery-cases', {
      incidentId: 'test-incident',
      householdRef: 'household-1',
      needs: ['shelter', 'food'],
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('creates cost code and entry, then reads burn-rate', async () => {
    const code = await postJSON('/api/cost-codes', {
      code: '5300',
      description: 'Emergency Operations',
      femaCategory: 'B',
    }, testOrgId);
    expect(code.status).toBe(201);
    const codeId = (code.body as { id: string }).id;

    const entry = await postJSON('/api/cost-entries', {
      costCodeId: codeId,
      amount: 5000,
      source: 'time',
      hours: 40,
    }, testOrgId);
    expect(entry.status).toBe(201);

    const burn = await fetchJSON('/api/finance/burn-rate', testOrgId);
    expect(burn.status).toBe(200);
    const data = burn.body as { totalCost: number; entryCount: number };
    expect(data.totalCost).toBeGreaterThan(0);
  });
});
