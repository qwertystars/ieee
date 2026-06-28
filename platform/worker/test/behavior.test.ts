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
    try {
      await env.db.prepare(stmt).run();
    } catch (e) {
      // tables may already exist
    }
  }
  migrationsRun = true;
}

async function fetchJSON(path: string, init?: RequestInit): Promise<{ status: number; body: unknown }> {
  const resp = await SELF.fetch(`https://test.local${path}`, init);
  const text = await resp.text(); let body: unknown; try { body = JSON.parse(text); } catch { body = text; }
  return { status: resp.status, body };
}

async function postJSON(path: string, data: unknown): Promise<{ status: number; body: unknown }> {
  return fetchJSON(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

async function patchJSON(path: string, data: unknown): Promise<{ status: number; body: unknown }> {
  return fetchJSON(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

let testOrgId = '';

beforeAll(async () => {
  await ensureMigrations();
  const seed = await postWithOrg('/api/seed/demo', {});
  testOrgId = (seed.body as { orgId: string }).orgId;
});

async function fetchWithOrg(path: string, init?: RequestInit): Promise<{ status: number; body: unknown }> {
  const headers = new Headers(init?.headers);
  if (testOrgId) headers.set('X-Org-Id', testOrgId);
  return fetchJSON(path, { ...init, headers });
}

async function postWithOrg(path: string, data: unknown): Promise<{ status: number; body: unknown }> {
  return fetchWithOrg(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

async function patchWithOrg(path: string, data: unknown): Promise<{ status: number; body: unknown }> {
  return fetchWithOrg(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

describe('Seed endpoint', () => {
  it('creates Rivertown demo data idempotently', async () => {
    const first = await postWithOrg('/api/seed/demo', {});
    expect(first.status).toBe(201);
    const firstBody = first.body as Record<string, unknown>;
    expect(firstBody.event).toBe('Rivertown Urban Flood');
    expect(firstBody.users).toBe(6);
    const second = await postWithOrg('/api/seed/demo', {});
    expect(second.status).toBe(201);
    const secondBody = second.body as Record<string, unknown>;
    expect(secondBody.users).toBe(6);
    expect(secondBody.incidentId).toBe(firstBody.incidentId);
  });
});

describe('Auth routes', () => {
  it('logs in with valid credentials', async () => {
    const result = await postWithOrg('/api/auth/login', { email: 'admin@demo.disaster', password: 'demo1234' });
    expect(result.status).toBe(200);
    const body = result.body as { token: string; user: { email: string } };
    expect(body.token).toBeTruthy();
    expect(body.user.email).toBe('admin@demo.disaster');
  });
  it('rejects invalid credentials', async () => {
    const result = await postWithOrg('/api/auth/login', { email: 'admin@demo.disaster', password: 'wrong' });
    expect(result.status).toBe(401);
  });
  it('returns /me with valid token', async () => {
    const login = await postWithOrg('/api/auth/login', { email: 'admin@demo.disaster', password: 'demo1234' });
    const token = (login.body as { token: string }).token;
    const me = await fetchWithOrg('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } });
    expect(me.status).toBe(200);
    expect((me.body as { email: string }).email).toBe('admin@demo.disaster');
  });
  it('rejects /me without token', async () => {
    const me = await fetchWithOrg('/api/auth/me');
    expect(me.status).toBe(401);
  });
});

describe('Events API', () => {
  it('lists events after seed', async () => {
    await postWithOrg('/api/seed/demo', {});
    const result = await fetchWithOrg('/api/events');
    expect(result.status).toBe(200);
    const body = result.body as { items: Array<{ type: string }> };
    expect(body.items.length).toBeGreaterThan(0);
    expect(body.items.some((e) => e.type === 'flood')).toBe(true);
  });
  it('returns 404 for unknown event', async () => {
    const result = await fetchWithOrg('/api/events/00000000000000000000000000');
    expect(result.status).toBe(404);
  });
});

describe('Reports API', () => {
  let incidentId: string;
  beforeAll(async () => {
    await postWithOrg('/api/seed/demo', {});
    const eventsResp = await fetchWithOrg('/api/events');
    incidentId = (eventsResp.body as { items: Array<{ incidentId: string }> }).items[0]!.incidentId;
  });
  it('creates a report with Point geometry', async () => {
    const result = await postWithOrg(`/api/events/${incidentId}/reports`, {
      reporterType: 'field_responder', reportCategory: 'flooding', description: 'Test flood report',
      geometry: { type: 'Point', coordinates: [-80.0, 26.0] }, urgency: 'high',
    });
    expect(result.status).toBe(201);
    const body = result.body as { id: string; verificationStatus: string; reportCategory: string };
    expect(body.id).toBeTruthy();
    expect(body.verificationStatus).toBe('unverified');
    expect(body.reportCategory).toBe('flooding');
  });
  it('rejects report with mismatched event_id', async () => {
    const result = await postWithOrg(`/api/events/${incidentId}/reports`, {
      eventId: '00000000000000000000000000', reporterType: 'field_responder', reportCategory: 'flooding',
      description: 'bad event', geometry: { type: 'Point', coordinates: [-80.0, 26.0] }, urgency: 'high',
    });
    expect(result.status).toBe(400);
  });
  it('rejects report without Point geometry', async () => {
    const result = await postWithOrg(`/api/events/${incidentId}/reports`, {
      reporterType: 'field_responder', reportCategory: 'flooding', description: 'no geometry',
      geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] }, urgency: 'high',
    });
    expect(result.status).toBe(400);
  });
  it('lists reports for an incident', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/reports`);
    expect(result.status).toBe(200);
    expect((result.body as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });
});

describe('Roads API', () => {
  let incidentId: string; let roadId: string;
  beforeAll(async () => {
    await postWithOrg('/api/seed/demo', {});
    const eventsResp = await fetchWithOrg('/api/events');
    incidentId = (eventsResp.body as { items: Array<{ incidentId: string }> }).items[0]!.incidentId;
    const roadsResp = await fetchWithOrg(`/api/events/${incidentId}/roads/status`);
    roadId = (roadsResp.body as { items: Array<{ id: string }> }).items[0]!.id;
  });
  it('lists road statuses', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/roads/status`);
    expect(result.status).toBe(200);
    expect((result.body as { items: unknown[] }).items.length).toBeGreaterThanOrEqual(2);
  });
  it('updates road status to blocked', async () => {
    const result = await patchWithOrg(`/api/roads/${roadId}/status`, { status: 'blocked', reason: 'Field report', confidenceScore: 0.9 });
    expect(result.status).toBe(200);
    const body = result.body as { status: string; confidenceScore: number };
    expect(body.status).toBe('blocked');
    expect(body.confidenceScore).toBe(0.9);
  });
  it('rejects invalid road status', async () => {
    const result = await patchWithOrg(`/api/roads/${roadId}/status`, { status: 'washed_away' });
    expect(result.status).toBe(422);
  });
});

describe('Tasks API', () => {
  let incidentId: string; let taskId: string;
  beforeAll(async () => {
    await postWithOrg('/api/seed/demo', {});
    const eventsResp = await fetchWithOrg('/api/events');
    incidentId = (eventsResp.body as { items: Array<{ incidentId: string }> }).items[0]!.incidentId;
    const tasksResp = await fetchWithOrg(`/api/events/${incidentId}/tasks`);
    taskId = (tasksResp.body as { items: Array<{ id: string }> }).items[0]!.id;
  });
  it('lists tasks', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/tasks`);
    expect(result.status).toBe(200);
    expect((result.body as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });
  it('accepts an assigned task', async () => {
    const result = await patchWithOrg(`/api/tasks/${taskId}`, { status: 'accepted' });
    expect(result.status).toBe(200);
    expect((result.body as { status: string }).status).toBe('accepted');
  });
  it('rejects illegal task transition', async () => {
    const result = await patchWithOrg(`/api/tasks/${taskId}`, { status: 'completed' });
    expect(result.status).toBe(409);
  });
});

describe('Dashboard API', () => {
  let incidentId: string;
  beforeAll(async () => {
    await postWithOrg('/api/seed/demo', {});
    const eventsResp = await fetchWithOrg('/api/events');
    incidentId = (eventsResp.body as { items: Array<{ incidentId: string }> }).items[0]!.incidentId;
  });
  it('returns dashboard summary', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/dashboard-summary`);
    expect(result.status).toBe(200);
    const body = result.body as Record<string, unknown>;
    expect(body).toHaveProperty('total_reports');
    expect(body).toHaveProperty('roads_blocked');
    expect(body).toHaveProperty('pending_tasks');
    expect(body).toHaveProperty('shelters_open');
    expect(body).toHaveProperty('last_updated');
  });
  it('returns map layers as arrays', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/map-layers`);
    expect(result.status).toBe(200);
    const body = result.body as Record<string, unknown[]>;
    expect(Array.isArray(body.reports)).toBe(true);
    expect(Array.isArray(body.roads)).toBe(true);
    expect(Array.isArray(body.teams)).toBe(true);
    expect(Array.isArray(body.shelters)).toBe(true);
  });
  it('rejects malformed bbox', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/map-layers?bbox=bad`);
    expect(result.status).toBe(400);
  });
  it('returns alerts list', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/alerts`);
    expect(result.status).toBe(200);
    expect(Array.isArray((result.body as { items: unknown[] }).items)).toBe(true);
  });
});

describe('Situation Report', () => {
  let incidentId: string;
  beforeAll(async () => {
    await postWithOrg('/api/seed/demo', {});
    const eventsResp = await fetchWithOrg('/api/events');
    incidentId = (eventsResp.body as { items: Array<{ incidentId: string }> }).items[0]!.incidentId;
  });
  it('returns text situation report', async () => {
    const result = await postWithOrg(`/api/events/${incidentId}/situation-report`, { format: 'text' });
    expect(result.status).toBe(200);
    expect(typeof result.body).toBe('string');
    expect(result.body as string).toContain('SITUATION REPORT');
  });
  it('returns 501 for PDF format', async () => {
    const result = await postWithOrg(`/api/events/${incidentId}/situation-report`, { format: 'pdf' });
    expect(result.status).toBe(501);
  });
});

describe('Recommendations API', () => {
  let incidentId: string; let recId: string;
  beforeAll(async () => {
    await postWithOrg('/api/seed/demo', {});
    const eventsResp = await fetchWithOrg('/api/events');
    incidentId = (eventsResp.body as { items: Array<{ incidentId: string }> }).items[0]!.incidentId;
    const recsResp = await fetchWithOrg(`/api/events/${incidentId}/recommendations`);
    recId = (recsResp.body as { items: Array<{ id: string }> }).items[0]!.id;
  });
  it('lists recommendations', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/recommendations`);
    expect(result.status).toBe(200);
    expect((result.body as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });
  it('approves a recommendation', async () => {
    const result = await postWithOrg(`/api/events/${incidentId}/recommendations/${recId}/approve`, {});
    expect(result.status).toBe(200);
    expect((result.body as { status: string }).status).toBe('approved');
  });
});

describe('Shelters API', () => {
  let incidentId: string; let shelterId: string;
  beforeAll(async () => {
    await postWithOrg('/api/seed/demo', {});
    const eventsResp = await fetchWithOrg('/api/events');
    incidentId = (eventsResp.body as { items: Array<{ incidentId: string }> }).items[0]!.incidentId;
    const sheltersResp = await fetchWithOrg(`/api/events/${incidentId}/shelters`);
    shelterId = (sheltersResp.body as { items: Array<{ id: string }> }).items[0]!.id;
  });
  it('lists shelters', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/shelters`);
    expect(result.status).toBe(200);
    expect((result.body as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });
  it('updates shelter status', async () => {
    const result = await patchWithOrg(`/api/shelters/${shelterId}/status`, { status: 'full' });
    expect(result.status).toBe(200);
    expect((result.body as { status: string }).status).toBe('full');
  });
});

describe('Health endpoints', () => {
  it('/healthz returns ok', async () => {
    const result = await fetchJSON('/healthz');
    expect(result.status).toBe(200);
    expect((result.body as { ok: boolean }).ok).toBe(true);
  });
  it('/healthz/deep checks D1 and KV', async () => {
    const result = await fetchJSON('/healthz/deep');
    expect(result.status).toBe(200);
    const body = result.body as { ok: boolean; checks: Record<string, { ok: boolean }> };
    expect(body.checks.db.ok).toBe(true);
    expect(body.checks.cache.ok).toBe(true);
  });
});

describe('Teams API', () => {
  let incidentId: string; let teamId: string;
  beforeAll(async () => {
    await postWithOrg('/api/seed/demo', {});
    const eventsResp = await fetchWithOrg('/api/events');
    incidentId = (eventsResp.body as { items: Array<{ incidentId: string }> }).items[0]!.incidentId;
    const teamsResp = await fetchWithOrg(`/api/events/${incidentId}/teams`);
    teamId = (teamsResp.body as { items: Array<{ id: string }> }).items[0]!.id;
  });
  it('lists teams', async () => {
    const result = await fetchWithOrg(`/api/events/${incidentId}/teams`);
    expect(result.status).toBe(200);
    expect((result.body as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });
  it('updates team location', async () => {
    const result = await patchWithOrg(`/api/teams/${teamId}/location`, { location: { type: 'Point', coordinates: [-80.05, 26.1] } });
    expect(result.status).toBe(200);
  });
  it('updates team status', async () => {
    const result = await patchWithOrg(`/api/teams/${teamId}/status`, { status: 'dispatched' });
    expect(result.status).toBe(200);
    expect((result.body as { status: string }).status).toBe('dispatched');
  });
});

describe('Durable Objects', () => {
  it('TaskTimer starts and cancels a timer', async () => {
    const id = env.TaskTimer.idFromName('test-task');
    const stub = env.TaskTimer.get(id);
    const startResp = await stub.fetch(new Request('https://do.local/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ taskId: 'test-task', slaMs: 60000 }) }));
    expect(startResp.status).toBe(200);
    const startBody = await startResp.json() as { ok: boolean; taskId: string };
    expect(startBody.ok).toBe(true);
    expect(startBody.taskId).toBe('test-task');
    const statusResp = await stub.fetch(new Request('https://do.local/status'));
    const statusBody = await statusResp.json() as { state: { status: string } };
    expect(statusBody.state.status).toBe('pending');
    const cancelResp = await stub.fetch(new Request('https://do.local/cancel', { method: 'POST' }));
    expect(cancelResp.status).toBe(200);
  });

  it('ShelterCounter manages occupancy', async () => {
    const id = env.ShelterCounter.idFromName('test-shelter');
    const stub = env.ShelterCounter.get(id);
    await stub.fetch(new Request('https://do.local/init', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ shelterId: 'test-shelter', totalCapacity: 100 }) }));
    const checkinResp = await stub.fetch(new Request('https://do.local/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ count: 10 }) }));
    const checkinBody = await checkinResp.json() as { ok: boolean; currentOccupancy: number };
    expect(checkinBody.ok).toBe(true);
    expect(checkinBody.currentOccupancy).toBe(10);
    const statusResp = await stub.fetch(new Request('https://do.local/status'));
    const statusBody = await statusResp.json() as { currentOccupancy: number; available: number };
    expect(statusBody.currentOccupancy).toBe(10);
    expect(statusBody.available).toBe(90);
  });

  it('ShelterCounter rejects over-capacity checkin', async () => {
    const id = env.ShelterCounter.idFromName('small-shelter');
    const stub = env.ShelterCounter.get(id);
    await stub.fetch(new Request('https://do.local/init', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ shelterId: 'small-shelter', totalCapacity: 5 }) }));
    const overResp = await stub.fetch(new Request('https://do.local/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ count: 10 }) }));
    expect(overResp.status).toBe(409);
  });

  it('AmbulanceQueue maintains priority order', async () => {
    const id = env.AmbulanceQueue.idFromName('test-queue');
    const stub = env.AmbulanceQueue.get(id);
    await stub.fetch(new Request('https://do.local/enqueue', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: 'req-low', patientLocation: { lat: 26, lng: -80 }, urgency: 'low', requestedAt: 1000 }) }));
    await stub.fetch(new Request('https://do.local/enqueue', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: 'req-critical', patientLocation: { lat: 26, lng: -80 }, urgency: 'critical', requestedAt: 2000 }) }));
    const peekResp = await stub.fetch(new Request('https://do.local/peek'));
    const peekBody = await peekResp.json() as { next: { id: string } };
    expect(peekBody.next.id).toBe('req-critical');
  });

  it('PasskeyDO stores and verifies challenges', async () => {
    const id = env.PasskeyDO.idFromName('test@example.com');
    const stub = env.PasskeyDO.get(id);
    const storeResp = await stub.fetch(new Request('https://do.local/challenge/store', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ challenge: 'test-challenge-123', userId: 'user-1', userEmail: 'test@example.com', type: 'registration' }) }));
    const storeBody = await storeResp.json() as { challengeId: string };
    const challengeId = storeBody.challengeId;
    const verifyResp = await stub.fetch(new Request('https://do.local/challenge/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ challengeId, challenge: 'test-challenge-123' }) }));
    const verifyBody = await verifyResp.json() as { ok: boolean; userId: string };
    expect(verifyBody.ok).toBe(true);
    expect(verifyBody.userId).toBe('user-1');
    const replayResp = await stub.fetch(new Request('https://do.local/challenge/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ challengeId, challenge: 'test-challenge-123' }) }));
    expect(replayResp.status).toBe(404);
  });

  it('RateLimiter enforces token bucket', async () => {
    const id = env.RateLimiter.idFromName('test-rate-limit');
    const stub = env.RateLimiter.get(id);
    const resp1 = await stub.fetch(new Request('https://do.local/?key=limit-test&limit=2&window=60'));
    expect((await resp1.json() as { allowed: boolean }).allowed).toBe(true);
    const resp2 = await stub.fetch(new Request('https://do.local/?key=limit-test&limit=2&window=60'));
    expect((await resp2.json() as { allowed: boolean }).allowed).toBe(true);
    const resp3 = await stub.fetch(new Request('https://do.local/?key=limit-test&limit=2&window=60'));
    expect(resp3.status).toBe(429);
    expect((await resp3.json() as { allowed: boolean }).allowed).toBe(false);
  });
});
