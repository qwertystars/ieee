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

describe('P6: Communications + Public Portal', () => {
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

  it('creates an alert (draft status)', async () => {
    const { status, body } = await postJSON('/api/alerts', {
      incidentId: 'test-incident',
      alertType: 'evacuation',
      title: 'Evacuation Alert',
      message: 'Evacuate immediately',
      severity: 'critical',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean; status: string };
    expect(data.status).toBe('draft');
  });

  it('approves alert and triggers fanout', async () => {
    const createResp = await postJSON('/api/alerts', {
      incidentId: 'test-incident',
      alertType: 'flood',
      title: 'Flood Warning',
      severity: 'warning',
    }, testOrgId);
    const alertId = (createResp.body as { id: string }).id;

    const { status, body } = await postJSON(`/api/alerts/${alertId}/approve`, {}, testOrgId);
    expect(status).toBe(200);
    const data = body as { ok: boolean; status: string };
    expect(data.ok).toBe(true);
    expect(data.status).toBe('fanout_started');
  });

  it('exports CAP v1.2 XML', async () => {
    const createResp = await postJSON('/api/alerts', {
      incidentId: 'test-incident',
      alertType: 'fire',
      title: 'Fire Alert',
      severity: 'critical',
    }, testOrgId);
    const alertId = (createResp.body as { id: string }).id;

    const resp = await SELF.fetch(`https://test.local/api/alerts/${alertId}/cap`, {
      headers: { 'X-Org-Id': testOrgId },
    });
    expect(resp.status).toBe(200);
    expect(resp.headers.get('Content-Type')).toBe('application/xml');
    const xml = await resp.text();
    expect(xml).toContain('<alert');
    expect(xml).toContain('urn:oasis:names:tc:emergency:CAP:1.2');
  });

  it('creates a comms draft', async () => {
    const { status, body } = await postJSON('/api/comms-drafts', {
      incidentId: 'test-incident',
      draftType: 'press_release',
      title: 'Press Release',
      content: 'This is a press release draft.',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });

  it('creates a public subscription', async () => {
    const { status, body } = await postJSON('/api/public/subscribe', {
      incidentId: 'test-incident',
      phone: '+1234567890',
      channels: ['sms'],
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });

  it('creates a webhook subscription', async () => {
    const { status, body } = await postJSON('/api/webhooks/subscribe', {
      url: 'https://example.com/webhook',
      events: ['alert.created', 'alert.approved'],
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; ok: boolean };
    expect(data.ok).toBe(true);
  });

  it('serves public status page', async () => {
    const resp = await SELF.fetch('https://test.local/api/public/status');
    expect(resp.status).toBe(200);
    const data = await resp.json() as { ok: boolean; activeAlerts: number };
    expect(data.ok).toBe(true);
    expect(data.activeAlerts).toBeGreaterThanOrEqual(0);
  });
});
