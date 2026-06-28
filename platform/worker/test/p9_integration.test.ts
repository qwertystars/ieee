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

describe('P9: Prediction/Simulation + Drone + Damage Assessment', () => {
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

  it('submits and runs a flood simulation', async () => {
    const submit = await postJSON('/api/scenarios', {
      incidentId: 'test-incident',
      modelType: 'flood',
      params: { waterLevel: 10, cells: [
        { lat: 40.7, lng: -74.0, elevation: 5 },
        { lat: 40.71, lng: -74.0, elevation: 15 },
        { lat: 40.72, lng: -74.0, elevation: 8 },
      ]},
      scenarioLabel: 'expected',
    }, testOrgId);
    expect(submit.status).toBe(201);
    const scenarioId = (submit.body as { id: string }).id;

    const run = await postJSON(`/api/scenarios/${scenarioId}/run-flood`, {}, testOrgId);
    expect(run.status).toBe(200);
    const data = run.body as { floodedCells: number; resultGeoJson: { features: unknown[] } };
    expect(data.floodedCells).toBe(2);
    expect(data.resultGeoJson.features.length).toBe(2);
  });

  it('creates a drone mission and flight', async () => {
    const mission = await postJSON('/api/drone/missions', {
      incidentId: 'test-incident',
      name: 'Survey Mission 1',
    }, testOrgId);
    expect(mission.status).toBe(201);
    const missionId = (mission.body as { id: string }).id;

    const flight = await postJSON(`/api/drone/missions/${missionId}/flights`, {
      mediaR2Key: 'media/test.jpg',
      mediaType: 'image',
      altitudeM: 100,
    }, testOrgId);
    expect(flight.status).toBe(201);
  });

  it('generates a search pattern', async () => {
    const { status, body } = await postJSON('/api/drone/search-pattern', {
      centerLat: 40.7,
      centerLng: -74.0,
      spacing: 100,
      turns: 3,
    }, testOrgId);
    expect(status).toBe(200);
    const data = body as { waypoints: { lat: number; lng: number }[]; pattern: string };
    expect(data.pattern).toBe('expanding_square');
    expect(data.waypoints.length).toBe(12);
  });

  it('creates a damage report with EXIF verification', async () => {
    const { status, body } = await postJSON('/api/damage-reports', {
      incidentId: 'test-incident',
      assetClass: 'building',
      severity: 'major',
      exifLat: 40.7128,
      exifLng: -74.0060,
      taggedLat: 40.7128,
      taggedLng: -74.0060,
      description: 'Severe structural damage',
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { id: string; exifVerified: boolean };
    expect(data.exifVerified).toBe(true);
  });

  it('rejects EXIF mismatch', async () => {
    const { status, body } = await postJSON('/api/damage-reports', {
      incidentId: 'test-incident',
      assetClass: 'road',
      severity: 'minor',
      exifLat: 40.7128,
      exifLng: -74.0060,
      taggedLat: 41.0,
      taggedLng: -74.5,
    }, testOrgId);
    expect(status).toBe(201);
    const data = body as { exifVerified: boolean };
    expect(data.exifVerified).toBe(false);
  });
});
