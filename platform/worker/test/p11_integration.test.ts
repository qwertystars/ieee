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

describe('P11: Security + Compliance + Admin + Developer Platform + Offline', () => {
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

  it('logs a security action', async () => {
    const { status, body } = await postJSON('/api/security/logs', {
      action: 'login_success',
      actor: 'user-1',
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('sets a retention policy', async () => {
    const { status, body } = await postJSON('/api/retention/policies', {
      dataClass: 'sensitive',
      ttlDays: 90,
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('records and revokes consent', async () => {
    const create = await postJSON('/api/consents', {
      personRef: 'person-1',
      purpose: 'marketing',
    }, testOrgId);
    expect(create.status).toBe(201);
    const id = (create.body as { id: string }).id;

    const revoke = await postJSON(`/api/consents/${id}/revoke`, {}, testOrgId);
    expect(revoke.status).toBe(200);
    expect((revoke.body as { ok: boolean }).ok).toBe(true);
  });

  it('creates and lists feature flags', async () => {
    const { status } = await postJSON('/api/feature-flags', {
      key: 'new_dashboard',
      enabled: true,
      scope: 'org',
    }, testOrgId);
    expect(status).toBe(201);

    const list = await fetchJSON('/api/feature-flags', testOrgId);
    expect(list.status).toBe(200);
    expect((list.body as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });

  it('creates an announcement', async () => {
    const { status, body } = await postJSON('/api/announcements', {
      message: 'System maintenance at 2am',
      level: 'warning',
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });

  it('creates a DSR request', async () => {
    const { status, body } = await postJSON('/api/dsr', {
      personRef: 'person-1',
      requestType: 'export',
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { status: string }).status).toBe('pending');
  });

  it('activates break-glass (time-boxed)', async () => {
    const { status, body } = await postJSON('/api/security/break-glass', {
      actor: 'admin-1',
      reason: 'Emergency access',
      durationMinutes: 15,
    }, testOrgId);
    expect(status).toBe(200);
    const data = body as { ok: boolean; token: string; expiresAt: number };
    expect(data.token).toBeDefined();
    expect(data.expiresAt).toBeGreaterThan(Date.now());
  });

  it('records a compliance record', async () => {
    const { status, body } = await postJSON('/api/compliance/records', {
      recordType: 'data_processing',
      data: { purpose: 'emergency_response' },
    }, testOrgId);
    expect(status).toBe(201);
    expect((body as { ok: boolean }).ok).toBe(true);
  });
});
