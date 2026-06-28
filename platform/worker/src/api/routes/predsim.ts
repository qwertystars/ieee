import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { scenarios, droneMissions, droneFlights, damageReports } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const predsimRoutes = new Hono<AppEnv>();

// T126: Submit scenario
predsimRoutes.post('/scenarios', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(scenarios).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    modelType: body.modelType as 'fire_spread' | 'flood' | 'smoke' | 'plume' | 'dam_break' | 'evac' | 'shelter_demand' | 'resource_demand' | 'hospital_surge' | 'seir' | 'congestion' | 'power_cascade' | 'comms_cascade',
    params: (body.params as Record<string, unknown>) ?? {},
    status: 'queued',
    scenarioLabel: ((body.scenarioLabel as string) ?? 'expected') as 'best' | 'expected' | 'worst',
    createdAt: nowMs(),
  });

  // Enqueue simulation via droneQ (reusing as simQ proxy)
  try {
    await c.env.droneQ.send({
      type: 'sim_run',
      scenarioId: id,
      orgId,
      modelType: body.modelType,
      params: body.params,
      __idempotencyKey: ulid(),
    });
  } catch { /* Queue may not be bound */ }

  return c.json({ id, ok: true, status: 'queued' }, 201);
});

// T126: Get scenario result
predsimRoutes.get('/scenarios/:id', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(scenarios).where(eq(scenarios.id, c.req.param('id'))).limit(1).all();
  if (!result[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Scenario not found', request_id: c.get('requestId') } }, 404);
  return c.json(result[0]);
});

// T127: Run simple flood simulation (bathtub fill)
predsimRoutes.post('/scenarios/:id/run-flood', async (c) => {
  const db = drizzle(c.env.db);
  const scenario = await db.select().from(scenarios).where(eq(scenarios.id, c.req.param('id'))).limit(1).all();
  if (!scenario[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Scenario not found', request_id: c.get('requestId') } }, 404);

  await db.update(scenarios).set({ status: 'running' }).where(eq(scenarios.id, scenario[0].id));

  const params = scenario[0].params ?? {};
  const waterLevel = (params.waterLevel as number) ?? 5;
  const cells = (params.cells as { lat: number; lng: number; elevation: number }[]) ?? [];

  const floodedCells = cells.filter((cell) => cell.elevation < waterLevel);
  const resultGeoJson = {
    type: 'FeatureCollection',
    features: floodedCells.map((cell) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [cell.lng, cell.lat] },
      properties: { depth: waterLevel - cell.elevation },
    })),
  };

  await db.update(scenarios).set({
    status: 'completed',
    resultGeoJson: JSON.stringify(resultGeoJson),
    confidence: 0.8,
    completedAt: nowMs(),
  }).where(eq(scenarios.id, scenario[0].id));

  return c.json({ ok: true, floodedCells: floodedCells.length, resultGeoJson });
});

// T129: Create drone mission
predsimRoutes.post('/drone/missions', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(droneMissions).values({
    id, orgId,
    incidentId: body.incidentId as string,
    name: body.name as string,
    surveyZone: (body.surveyZone as string) ?? null,
    status: 'planned',
    operatorId: (body.operatorId as string) ?? null,
    batteryLevel: 100,
    noFlyWarning: false,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T129: Record drone flight
predsimRoutes.post('/drone/missions/:id/flights', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(droneFlights).values({
    id, orgId,
    missionId: c.req.param('id'),
    startTime: (body.startTime as number) ?? nowMs(),
    endTime: (body.endTime as number) ?? null,
    mediaR2Key: (body.mediaR2Key as string) ?? null,
    mediaType: ((body.mediaType as string) ?? 'image') as 'image' | 'thermal' | 'video' | 'orthomosaic',
    cogR2Key: (body.cogR2Key as string) ?? null,
    altitudeM: (body.altitudeM as number) ?? null,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T130: Generate search pattern (expanding square)
predsimRoutes.post('/drone/search-pattern', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const centerLat = body.centerLat as number;
  const centerLng = body.centerLng as number;
  const spacing = (body.spacing as number) ?? 100;
  const turns = (body.turns as number) ?? 5;

  const waypoints: { lat: number; lng: number }[] = [];
  let lat = centerLat;
  let lng = centerLng;
  for (let i = 0; i < turns; i++) {
    const offset = (spacing / 111000) * (i + 1);
    waypoints.push({ lat: lat + offset, lng });
    waypoints.push({ lat: lat + offset, lng: lng + offset });
    waypoints.push({ lat, lng: lng + offset });
    waypoints.push({ lat, lng });
  }

  return c.json({ waypoints, pattern: 'expanding_square' });
});

// T131: Create damage report
predsimRoutes.post('/damage-reports', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const exifLat = body.exifLat as number | undefined;
  const exifLng = body.exifLng as number | undefined;
  const taggedLat = body.taggedLat as number | undefined;
  const taggedLng = body.taggedLng as number | undefined;
  const exifVerified = exifLat !== undefined && taggedLat !== undefined
    ? Math.abs(exifLat - taggedLat) < 0.001 && Math.abs((exifLng ?? 0) - (taggedLng ?? 0)) < 0.001
    : false;

  await db.insert(damageReports).values({
    id, orgId,
    incidentId: body.incidentId as string,
    assetClass: body.assetClass as 'building' | 'road' | 'bridge' | 'utility' | 'crop' | 'industrial' | 'shelter' | 'hospital' | 'school',
    severity: body.severity as 'affected' | 'minor' | 'major' | 'destroyed',
    location: (body.location as string) ?? null,
    photoR2Key: (body.photoR2Key as string) ?? null,
    exifLat: exifLat ?? null,
    exifLng: exifLng ?? null,
    exifVerified,
    description: (body.description as string) ?? null,
    estimatedLoss: (body.estimatedLoss as number) ?? null,
    repairPriority: (body.repairPriority as number) ?? null,
    verificationStatus: 'pending',
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: body.incidentId as string, actor: orgId, action: 'damage.reported', entity: `damage:${id}`, after: body });
  return c.json({ id, ok: true, exifVerified }, 201);
});

// T132: List damage reports
predsimRoutes.get('/damage-reports', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(damageReports.orgId, orgId) : sql`1=1`];
  if (incidentId) conditions.push(eq(damageReports.incidentId, incidentId));
  const result = await db.select().from(damageReports).where(and(...conditions)).orderBy(desc(damageReports.createdAt)).all();
  return c.json({ items: result });
});
