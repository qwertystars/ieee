import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { rawReports, ingestLogs, feedSources, weatherObs, weatherForecasts, weatherIndices, popEstimates, popNeeds, popH3 } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const ingestionRoutes = new Hono<AppEnv>();

// T75: Ingest a raw report (via queue or direct)
ingestionRoutes.post('/ingest', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const source = body.source as string;
  const externalId = (body.externalId as string) ?? ulid();

  // Idempotency: check (source, external_id)
  const existing = await db.select().from(rawReports)
    .where(and(eq(rawReports.source, source), eq(rawReports.externalId, externalId))).limit(1).all();
  if (existing[0]) {
    return c.json({ id: existing[0].id, ok: true, duplicate: true });
  }

  const id = ulid();
  const logId = ulid();
  await db.insert(rawReports).values({
    id, orgId,
    source,
    externalId,
    payload: body.payload as Record<string, unknown>,
    geo: (body.geo as string) ?? null,
    observedAt: (body.observedAt as number) ?? nowMs(),
    confidence: (body.confidence as number) ?? 0.5,
    status: 'staged',
    ingestLogId: logId,
    createdAt: nowMs(),
  });

  await db.insert(ingestLogs).values({
    id: logId, orgId,
    source,
    externalId,
    action: 'stage',
    result: 'ok',
    createdAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'ingest.stage', entity: `raw_report:${id}`, after: { source, externalId } });
  return c.json({ id, ok: true }, 201);
});

// T75: Promote validated reports
ingestionRoutes.post('/ingest/:id/promote', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const report = await db.select().from(rawReports).where(eq(rawReports.id, c.req.param('id'))).limit(1).all();
  if (!report[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Report not found', request_id: c.get('requestId') } }, 404);

  await db.update(rawReports).set({ status: 'promoted' }).where(eq(rawReports.id, report[0].id));
  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'ingest.promote', entity: `raw_report:${report[0].id}`, after: {} });
  return c.json({ ok: true });
});

// T75: Replay ingest log
ingestionRoutes.post('/ingest/replay/:logId', async (c) => {
  const db = drizzle(c.env.db);
  const log = await db.select().from(ingestLogs).where(eq(ingestLogs.id, c.req.param('logId'))).limit(1).all();
  if (!log[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Log not found', request_id: c.get('requestId') } }, 404);

  // Replay = find the raw report and re-process
  const report = await db.select().from(rawReports)
    .where(and(eq(rawReports.source, log[0].source), eq(rawReports.externalId, log[0].externalId ?? ''))).limit(1).all();
  if (report[0]) {
    await db.update(rawReports).set({ status: 'promoted' }).where(eq(rawReports.id, report[0].id));
  }
  return c.json({ ok: true, replayed: true });
});

// T75: HMAC webhook ingest
ingestionRoutes.post('/ingest/webhook', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const source = c.req.query('source') ?? 'webhook';
  const hmacSig = c.req.header('X-Signature');
  if (!hmacSig) return c.json({ error: { code: 'UNAUTHORIZED', message: 'Missing HMAC signature', request_id: c.get('requestId') } }, 401);

  const rawBody = await c.req.text();
  const feedSource = await db.select().from(feedSources)
    .where(and(eq(feedSources.orgId, orgId), eq(feedSources.name, source))).limit(1).all();

  const secret = (feedSource[0]?.config as { secret?: string } | null)?.secret;
  if (!secret) {
    return c.json({ error: { code: 'UNAUTHORIZED', message: 'No shared secret registered for source', request_id: c.get('requestId') } }, 401);
  }

  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(rawBody));
  const expected = Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, '0')).join('');

  if (!timingSafeEqual(expected, hmacSig)) {
    return c.json({ error: { code: 'UNAUTHORIZED', message: 'Invalid HMAC signature', request_id: c.get('requestId') } }, 401);
  }

  const body = JSON.parse(rawBody) as Record<string, unknown>;
  const externalId = (body.externalId as string) ?? ulid();

  const existing = await db.select().from(rawReports)
    .where(and(eq(rawReports.source, source), eq(rawReports.externalId, externalId))).limit(1).all();
  if (existing[0]) {
    return c.json({ id: existing[0].id, ok: true, duplicate: true });
  }

  const id = ulid();
  const logId = ulid();
  await db.insert(rawReports).values({
    id, orgId,
    source,
    externalId,
    payload: body,
    observedAt: nowMs(),
    confidence: 0.7,
    status: 'staged',
    ingestLogId: logId,
    createdAt: nowMs(),
  });

  await db.insert(ingestLogs).values({
    id: logId, orgId,
    source,
    externalId,
    action: 'stage',
    result: 'ok',
    createdAt: nowMs(),
  });

  if (feedSource[0]) {
    await db.update(feedSources).set({ lastSuccessAt: nowMs(), lastError: null }).where(eq(feedSources.id, feedSource[0].id));
  }

  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'ingest.webhook', entity: `raw_report:${id}`, after: { source, externalId } });
  return c.json({ id, ok: true }, 201);
});

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

// T76: File upload ingest (simplified — parses CSV/JSON arrays)
ingestionRoutes.post('/ingest/upload', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const contentType = c.req.header('Content-Type') ?? 'application/json';

  let records: Record<string, unknown>[] = [];
  if (contentType.includes('csv')) {
    const text = await c.req.text();
    const lines = text.split('\n').filter((l) => l.trim());
    if (lines.length < 2) return c.json({ error: 'Empty CSV' }, 400);
    const headers = lines[0]!.split(',').map((h) => h.trim());
    for (let i = 1; i < lines.length; i++) {
      const values = lines[i]!.split(',');
      const record: Record<string, unknown> = {};
      headers.forEach((h, j) => { record[h] = values[j]?.trim() ?? ''; });
      records.push(record);
    }
  } else {
    const body = await c.req.json().catch(() => []);
    records = Array.isArray(body) ? body : [body];
  }

  const inserted: string[] = [];
  const quarantined: unknown[] = [];
  for (const record of records) {
    if (!record.source && !record.externalId) { quarantined.push(record); continue; }
    const id = ulid();
    try {
      await db.insert(rawReports).values({
        id, orgId,
        source: (record.source as string) ?? 'upload',
        externalId: (record.externalId as string) ?? ulid(),
        payload: record,
        observedAt: (record.observedAt as number) ?? nowMs(),
        confidence: 0.6,
        status: 'staged',
        createdAt: nowMs(),
      });
      inserted.push(id);
    } catch { quarantined.push(record); }
  }

  return c.json({ inserted: inserted.length, quarantined: quarantined.length, ids: inserted }, 201);
});

// T77: List feed sources
ingestionRoutes.get('/feeds', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(feedSources).where(orgId ? eq(feedSources.orgId, orgId) : sql`1=1`).all();
  return c.json({ items: result });
});

// T77: Register a feed source
ingestionRoutes.post('/feeds', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(feedSources).values({
    id, orgId,
    name: body.name as string,
    kind: body.kind as 'weather' | 'seismic' | 'river' | 'fire' | 'satellite' | 'road' | 'call' | 'cap' | 'rss',
    url: (body.url as string) ?? null,
    config: (body.config as Record<string, unknown>) ?? {},
    enabled: true,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T83: Get latest weather for incident
ingestionRoutes.get('/weather/:incidentId', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const obs = await db.select().from(weatherObs)
    .where(and(eq(weatherObs.incidentId, c.req.param('incidentId')), orgId ? eq(weatherObs.orgId, orgId) : sql`1=1`))
    .orderBy(desc(weatherObs.observedAt)).limit(1).all();
  const forecast = await db.select().from(weatherForecasts)
    .where(and(eq(weatherForecasts.incidentId, c.req.param('incidentId')), orgId ? eq(weatherForecasts.orgId, orgId) : sql`1=1`))
    .orderBy(desc(weatherForecasts.forecastAt)).limit(24).all();
  const indices = await db.select().from(weatherIndices)
    .where(and(eq(weatherIndices.incidentId, c.req.param('incidentId')), orgId ? eq(weatherIndices.orgId, orgId) : sql`1=1`))
    .orderBy(desc(weatherIndices.createdAt)).limit(1).all();
  return c.json({ current: obs[0] ?? null, forecast, indices: indices[0] ?? null });
});

// T83: Record weather observation
ingestionRoutes.post('/weather/obs', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(weatherObs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    lat: (body.lat as number) ?? null,
    lng: (body.lng as number) ?? null,
    tempC: (body.tempC as number) ?? null,
    feelsLikeC: (body.feelsLikeC as number) ?? null,
    humidity: (body.humidity as number) ?? null,
    windSpeedKmh: (body.windSpeedKmh as number) ?? null,
    windDirDeg: (body.windDirDeg as number) ?? null,
    rainMm: (body.rainMm as number) ?? null,
    pressureHpa: (body.pressureHpa as number) ?? null,
    uvIndex: (body.uvIndex as number) ?? null,
    heatIndexC: (body.heatIndexC as number) ?? null,
    airQuality: (body.airQuality as number) ?? null,
    source: (body.source as string) ?? 'manual',
    observedAt: (body.observedAt as number) ?? nowMs(),
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T84: Compute weather risk indices
ingestionRoutes.post('/weather/:incidentId/indices', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const obs = await db.select().from(weatherObs)
    .where(and(eq(weatherObs.incidentId, c.req.param('incidentId')), orgId ? eq(weatherObs.orgId, orgId) : sql`1=1`))
    .orderBy(desc(weatherObs.observedAt)).limit(24).all();

  if (obs.length === 0) return c.json({ error: 'No weather data' }, 404);

  // Simple FWI proxy: temp × (1 - humidity/100)
  const avgTemp = obs.reduce((s, o) => s + (o.tempC ?? 0), 0) / obs.length;
  const avgHumidity = obs.reduce((s, o) => s + (o.humidity ?? 50), 0) / obs.length;
  const totalRain = obs.reduce((s, o) => s + (o.rainMm ?? 0), 0);
  const fwi = avgTemp > 0 ? avgTemp * (1 - avgHumidity / 100) : 0;

  // Flood risk: inverse of rain deficit + high humidity
  const floodRisk = Math.min(1, (totalRain / 100) + (avgHumidity / 200));

  // Heatwave risk: temp based
  const heatwaveRisk = avgTemp > 35 ? 1 : avgTemp > 30 ? 0.7 : avgTemp > 25 ? 0.3 : 0;

  // Landslide risk: rain + slope proxy (rain heavy)
  const landslideRisk = totalRain > 50 ? 0.8 : totalRain > 20 ? 0.4 : 0.1;

  const opRiskScore = Math.max(fwi / 30, floodRisk, heatwaveRisk, landslideRisk);

  const id = ulid();
  await db.insert(weatherIndices).values({
    id, orgId,
    incidentId: c.req.param('incidentId'),
    fwi: Math.round(fwi * 100) / 100,
    floodRisk: Math.round(floodRisk * 100) / 100,
    landslideRisk: Math.round(landslideRisk * 100) / 100,
    heatwaveRisk: Math.round(heatwaveRisk * 100) / 100,
    smokeEstimate: 0,
    plumeEstimate: 0,
    opRiskScore: Math.round(opRiskScore * 100) / 100,
    createdAt: nowMs(),
  });

  return c.json({ id, fwi, floodRisk, landslideRisk, heatwaveRisk, opRiskScore });
});

// T85: Preload pop_h3 cells
ingestionRoutes.post('/pop/preload', async (c) => {
  const body = await c.req.json().catch(() => ({ cells: [] as { h3: string; pop: number }[] }));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const cells = body.cells as { h3: string; pop: number }[];
  let inserted = 0;
  for (const cell of cells) {
    try {
      await db.insert(popH3).values({
        h3: cell.h3, orgId, pop: cell.pop,
        source: 'kontur', createdAt: nowMs(),
      }).onConflictDoNothing();
      inserted++;
    } catch { /* skip dups */ }
  }
  return c.json({ inserted, total: cells.length }, 201);
});

// T85: Estimate affected population for a zone (H3 cells list)
ingestionRoutes.post('/pop/estimate', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const h3Cells = body.h3Cells as string[];
  const incidentId = body.incidentId as string;

  if (!h3Cells || h3Cells.length === 0) return c.json({ totalAffected: 0 });

  // Cap: if >50,000 cells, reject with guidance
  if (h3Cells.length > 50000) {
    return c.json({
      error: {
        code: 'AOI_TOO_LARGE',
        message: `AOI covers ${h3Cells.length} H3 cells (cap: 50,000). Split into sub-polygons or downsample to H3 res 7.`,
        request_id: c.get('requestId'),
      },
    }, 413);
  }

  // Query pop_h3 for the given cells
  const placeholders = h3Cells.map(() => '?').join(',');
  const result = await c.env.db.prepare(`SELECT SUM(pop) as total FROM pop_h3 WHERE h3 IN (${placeholders})`).bind(...h3Cells).first<{ total: number | null }>();
  const totalAffected = result?.total ?? 0;

  // Demographic splits (configurable ratios, defaults from census)
  const elderly = Math.round(totalAffected * 0.15);
  const children = Math.round(totalAffected * 0.25);
  const disabled = Math.round(totalAffected * 0.08);
  const households = Math.round(totalAffected / 3.5);
  const buildings = Math.round(totalAffected / 4);

  const id = ulid();
  await db.insert(popEstimates).values({
    id, orgId,
    incidentId,
    zoneId: (body.zoneId as string) ?? null,
    totalAffected,
    elderly,
    children,
    disabled,
    households,
    buildings,
    confidence: 0.8,
    createdAt: nowMs(),
  });

  return c.json({ id, totalAffected, elderly, children, disabled, households, buildings, confidence: 0.8 }, 201);
});

// T87: Estimate needs (Sphere standards)
ingestionRoutes.post('/pop/needs', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const incidentId = body.incidentId as string;
  const totalAffected = (body.totalAffected as number) ?? 0;

  // Sphere standards: 15L water/person/day
  // Evac ratio: 30% of affected; shelter: 60% of evac; medical: 5%; food: 100%
  const evacNeeded = Math.round(totalAffected * 0.3);
  const shelterNeeded = Math.round(evacNeeded * 0.6);
  const medicalNeeded = Math.round(totalAffected * 0.05);
  const foodNeeded = totalAffected;
  const waterLitersNeeded = totalAffected * 15;
  const trapped = Math.round(totalAffected * 0.02);
  const unreachable = Math.round(totalAffected * 0.1);

  const id = ulid();
  await db.insert(popNeeds).values({
    id, orgId,
    incidentId,
    zoneId: (body.zoneId as string) ?? null,
    evacNeeded,
    shelterNeeded,
    medicalNeeded,
    foodNeeded,
    waterLitersNeeded,
    trapped,
    unreachable,
    source: 'estimate',
    createdAt: nowMs(),
  });

  return c.json({ id, evacNeeded, shelterNeeded, medicalNeeded, foodNeeded, waterLitersNeeded, trapped, unreachable }, 201);
});
