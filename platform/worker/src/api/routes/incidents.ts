import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { incidents, incidentNotes, incidentTags, incidentTeams, incidentLinks, incidentAttachments, mapLayers, mapZones } from '../../db/schema';
import { eq, desc } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';
import { recordIdempotency } from '../../lib/idempotency';
import { onIncidentCreate } from '../../lib/onIncidentCreate';

export const incidentRoutes = new Hono<AppEnv>();

const DISASTER_TYPES = [
  'wildfire','flood','cyclone','earthquake','landslide','chemical_spill','heatwave',
  'power_outage','civil_emergency','disease_outbreak','tsunami','tornado','avalanche',
  'drought','building_collapse','crowd_crush','industrial_fire','oil_spill','radiological','custom',
];

incidentRoutes.get('/', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(incidents)
    .where(orgId ? eq(incidents.orgId, orgId) : eq(incidents.id, incidents.id))
    .orderBy(desc(incidents.createdAt)).limit(50).all();
  return c.json({ items: result });
});

incidentRoutes.get('/:id', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(incidents).where(eq(incidents.id, c.req.param('id'))).limit(1).all();
  const inc = result[0];
  if (!inc) return c.json({ error: { code: 'NOT_FOUND', message: 'Incident not found', request_id: c.get('requestId') } }, 404);
  if (inc.mergedIntoId) {
    return c.json({ error: { code: 'MERGED', message: `Incident merged into ${inc.mergedIntoId}`, request_id: c.get('requestId') } }, 301, { Location: `/api/incidents/${inc.mergedIntoId}` });
  }
  return c.json(inc);
});

incidentRoutes.post('/', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const type = body.type as string;
  if (!type || !DISASTER_TYPES.includes(type)) {
    return c.json({ error: { code: 'INVALID_TYPE', message: `Type must be one of: ${DISASTER_TYPES.join(', ')}`, request_id: c.get('requestId') } }, 400);
  }

  const idempKey = c.req.header('Idempotency-Key');
  if (idempKey) {
    const existing = await recordIdempotency(drizzle(c.env.db), 'incident_create', idempKey, { id: 'pending' });
    if (existing && typeof existing === 'object' && 'id' in existing && existing.id !== 'pending') {
      return c.json(existing, 200);
    }
  }

  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const values: typeof incidents.$inferInsert = {
    id, orgId, type,
    severity: ((body.severity as string) ?? 'moderate') as 'minor' | 'moderate' | 'severe' | 'catastrophic',
    status: 'monitoring',
    title: body.title as string,
    description: body.description as string | null,
    geometry: body.geometry ? JSON.stringify(body.geometry) : null,
    startsAt: body.startsAt as number | null,
    expectedEnd: body.expectedEnd as number | null,
    config: body.config as Record<string, unknown> | null,
    declarationLevel: ((body.declarationLevel as string) ?? 'none') as 'none' | 'advisory' | 'local' | 'state' | 'national',
    commandOwnerId: body.commandOwnerId as string | null,
    createdAt: nowMs(), updatedAt: nowMs(),
  };
  await db.insert(incidents).values(values);

  const doId = c.env.IncidentRoom.idFromName(id);
  const doStub = c.env.IncidentRoom.get(doId);
  await doStub.fetch(new Request('https://do.local/state'));

  await writeAudit({ db, orgId, actor: c.get('orgId') ?? 'system', action: 'incident.create', entity: `incident:${id}`, after: body });

  c.executionCtx.waitUntil(onIncidentCreate(c.env, id, orgId));

  if (idempKey) await recordIdempotency(db, 'incident_create', idempKey, { id });

  return c.json({ id, type, title: body.title, doSpawned: true }, 201);
});

incidentRoutes.post('/:id/notes', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: body.authorId ?? 'system', body: body.body ?? '', createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});

incidentRoutes.post('/:id/tags', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentTags).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    tag: body.tag ?? '', createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});

incidentRoutes.post('/:id/teams', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentTeams).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    teamId: body.teamId ?? '', role: body.role ?? null, createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});

incidentRoutes.post('/:id/attachments', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentAttachments).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    r2Key: body.r2Key ?? '', name: body.name ?? '', kind: body.kind ?? 'file', createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});

incidentRoutes.post('/:id/merge', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const targetId = body.targetId as string;
  const sourceId = c.req.param('id');
  const db = drizzle(c.env.db);

  await db.update(incidents).set({ mergedIntoId: targetId, updatedAt: nowMs() }).where(eq(incidents.id, sourceId));
  await db.update(incidentLinks).set({ parentId: targetId }).where(eq(incidentLinks.parentId, sourceId));

  await writeAudit({ db, orgId: c.get('orgId') ?? 'system', actor: c.get('orgId') ?? 'system', action: 'incident.merge', entity: `incident:${sourceId}`, after: { targetId } });
  return c.json({ ok: true, merged: sourceId, into: targetId });
});

incidentRoutes.post('/:id/clone', async (c) => {
  const db = drizzle(c.env.db);
  const source = await db.select().from(incidents).where(eq(incidents.id, c.req.param('id'))).limit(1).all();
  if (!source[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Source incident not found', request_id: c.get('requestId') } }, 404);

  const { id: _srcId, ...rest } = source[0]!;
  const id = ulid();
  await db.insert(incidents).values({
    ...rest, id, title: `${rest.title} (clone)`, status: 'monitoring', mergedIntoId: null,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id }, 201);
});

incidentRoutes.get('/:id/summary', async (c) => {
  const db = drizzle(c.env.db);
  const inc = await db.select().from(incidents).where(eq(incidents.id, c.req.param('id'))).limit(1).all();
  if (!inc[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Incident not found', request_id: c.get('requestId') } }, 404);

  const [notes, tags, teams, zones, layers] = await Promise.all([
    db.select().from(incidentNotes).where(eq(incidentNotes.incidentId, c.req.param('id'))).limit(20).all(),
    db.select().from(incidentTags).where(eq(incidentTags.incidentId, c.req.param('id'))).limit(20).all(),
    db.select().from(incidentTeams).where(eq(incidentTeams.incidentId, c.req.param('id'))).limit(20).all(),
    db.select().from(mapZones).where(eq(mapZones.incidentId, c.req.param('id'))).limit(50).all(),
    db.select().from(mapLayers).where(eq(mapLayers.incidentId, c.req.param('id'))).limit(20).all(),
  ]);

  return c.json({
    incident: inc[0], notesCount: notes.length, tags, teamsCount: teams.length,
    zonesCount: zones.length, layersCount: layers.length,
  });
});

incidentRoutes.get('/:id/ws', async (c) => {
  const id = c.req.param('id');
  const doId = c.env.IncidentRoom.idFromName(id);
  const doStub = c.env.IncidentRoom.get(doId);
  return doStub.fetch(c.req.raw);
});

incidentRoutes.get('/:id/presence', async (c) => {
  const doId = c.env.IncidentRoom.idFromName(c.req.param('id'));
  const doStub = c.env.IncidentRoom.get(doId);
  return doStub.fetch(new Request('https://do.local/presence'));
});

incidentRoutes.post('/:id/broadcast', async (c) => {
  const doId = c.env.IncidentRoom.idFromName(c.req.param('id'));
  const doStub = c.env.IncidentRoom.get(doId);
  return doStub.fetch(c.req.raw);
});
