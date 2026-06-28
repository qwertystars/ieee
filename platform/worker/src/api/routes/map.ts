import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { mapLayers, mapZones } from '../../db/schema';
import { eq } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const mapRoutes = new Hono<AppEnv>();

const BASE_LAYERS = ['satellite', 'street', 'terrain', 'dark', 'offline', 'custom'];

mapRoutes.get('/:incidentId/layers', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(mapLayers)
    .where(eq(mapLayers.incidentId, c.req.param('incidentId')))
    .orderBy(mapLayers.sort).all();
  return c.json({ items: result, baseLayers: BASE_LAYERS });
});

mapRoutes.post('/:incidentId/layers', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(mapLayers).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('incidentId'),
    name: body.name as string, kind: body.kind as string, source: body.source as string,
    style: body.style as Record<string, unknown> | null,
    visibility: (body.visibility as 'public' | 'internal' | 'sensitive') ?? 'internal',
    reviewStatus: 'draft', sort: (body.sort as number) ?? 0, version: 1,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id }, 201);
});

mapRoutes.patch('/:incidentId/layers/:layerId', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  await db.update(mapLayers).set({
    ...(body.name ? { name: body.name as string } : {}),
    ...(body.sort !== undefined ? { sort: body.sort as number } : {}),
    ...(body.visibility ? { visibility: body.visibility as 'public' | 'internal' | 'sensitive' } : {}),
    updatedAt: nowMs(),
  }).where(eq(mapLayers.id, c.req.param('layerId')));
  return c.json({ ok: true });
});

mapRoutes.delete('/:incidentId/layers/:layerId', async (c) => {
  const db = drizzle(c.env.db);
  await db.delete(mapLayers).where(eq(mapLayers.id, c.req.param('layerId')));
  return c.json({ ok: true });
});

const ZONE_TYPES = [
  'evacuation', 'shelter_catchment', 'road_closure', 'danger', 'safe',
  'search', 'responder_staging', 'medical_triage', 'no_entry', 'supply_drop',
  'drone_survey', 'predicted_spread',
];

mapRoutes.get('/:incidentId/zones', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(mapZones)
    .where(eq(mapZones.incidentId, c.req.param('incidentId'))).all();
  return c.json({ items: result, zoneTypes: ZONE_TYPES });
});

mapRoutes.post('/:incidentId/zones', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const zoneType = body.zoneType as string;
  if (!ZONE_TYPES.includes(zoneType)) {
    return c.json({ error: { code: 'INVALID_ZONE_TYPE', message: `Must be one of: ${ZONE_TYPES.join(', ')}`, request_id: c.get('requestId') } }, 400);
  }
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(mapZones).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('incidentId'),
    zoneType, geometry: body.geometry as string,
    style: body.style as Record<string, unknown> | null,
    reviewStatus: 'draft', createdAt: nowMs(), updatedAt: nowMs(),
  });
  await writeAudit({ db, orgId: c.get('orgId') ?? 'system', actor: c.get('orgId') ?? 'system', action: 'map.zone.create', entity: `zone:${id}`, after: body });
  return c.json({ id, zoneType, reviewStatus: 'draft' }, 201);
});

mapRoutes.patch('/:incidentId/zones/:zoneId', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  await db.update(mapZones).set({
    ...(body.geometry ? { geometry: body.geometry as string } : {}),
    ...(body.reviewStatus ? { reviewStatus: body.reviewStatus as 'draft' | 'reviewed' | 'official' } : {}),
    updatedAt: nowMs(),
  }).where(eq(mapZones.id, c.req.param('zoneId')));
  return c.json({ ok: true });
});

mapRoutes.delete('/:incidentId/zones/:zoneId', async (c) => {
  const db = drizzle(c.env.db);
  await db.delete(mapZones).where(eq(mapZones.id, c.req.param('zoneId')));
  return c.json({ ok: true });
});

mapRoutes.get('/:incidentId/overlays', async (c) => {
  const overlays = [
    'heatmap', 'population_density', 'building_footprints', 'road_network',
    'pois', 'power_grid', 'water_supply', 'railway', 'bridge', 'floodplain',
    'elevation', 'wind', 'rain', 'temperature', 'air_quality',
    'responder', 'vehicle', 'drone', 'request', 'shelter', 'hospital',
    'cell_tower', 'hazard_plume', 'wind_particles', 'isochrone', 'geofence',
  ];
  return c.json({ overlays });
});
