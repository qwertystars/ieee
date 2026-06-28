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

describe('P7: AI Configuration + Reports', () => {
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

  it('creates a prompt version', async () => {
    const { status, body } = await postJSON('/api/prompts', {
      name: 'incident_summary',
      body: 'Summarize incident {{incidentId}}',
      temperature: 0.5,
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; version: number; ok: boolean };
    expect(data.version).toBe(1);
    expect(data.ok).toBe(true);
  });

  it('generates AI output as draft', async () => {
    const { status, body } = await postJSON('/api/ai/generate', {
      incidentId: 'test-incident',
      promptName: 'incident_summary',
      output: { summary: 'Test summary' },
      confidence: 0.8,
      citations: ['row-1', 'row-2'],
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; reviewStatus: string };
    expect(data.reviewStatus).toBe('draft');
  });

  it('approves AI output', async () => {
    const gen = await postJSON('/api/ai/generate', {
      promptName: 'test',
      output: { test: true },
    }, testOrgId);
    const id = (gen.body as { id: string }).id;
    const { status, body } = await postJSON(`/api/ai/outputs/${id}/approve`, {}, testOrgId);
    expect(status).toBe(200);
    const data = body as { reviewStatus: string };
    expect(data.reviewStatus).toBe('official');
  });

  it('creates and retrieves a report', async () => {
    const { status, body } = await postJSON('/api/ai/reports', {
      incidentId: 'test-incident',
      title: 'Sitrep #1',
      reportType: 'sitrep',
      contentMd: '# Situation Report\n\nAll clear.',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; shareToken: string };
    expect(data.shareToken).toBeDefined();

    const get = await fetchJSON(`/api/ai/reports/${data.id}`, testOrgId);
    expect(get.status).toBe(200);
    const report = get.body as { title: string };
    expect(report.title).toBe('Sitrep #1');
  });

  it('exports report as markdown', async () => {
    const create = await postJSON('/api/ai/reports', {
      title: 'Export Test',
      reportType: 'sitrep',
      contentMd: '# Export\nContent here.',
    }, testOrgId);
    const id = (create.body as { id: string }).id;
    const resp = await SELF.fetch(`https://test.local/api/ai/reports/${id}/export?format=md`, {
      headers: { 'X-Org-Id': testOrgId },
    });
    expect(resp.status).toBe(200);
    expect(resp.headers.get('Content-Type')).toBe('text/markdown');
    const md = await resp.text();
    expect(md).toContain('# Export');
  });

  it('returns AI monitor stats', async () => {
    const { status, body } = await fetchJSON('/api/ai/monitor', testOrgId);
    expect(status).toBe(200);
    const data = body as { totalCalls: number; successRate: number; avgLatencyMs: number };
    expect(data.totalCalls).toBeGreaterThanOrEqual(0);
    expect(data.successRate).toBeGreaterThanOrEqual(0);
  });
});
