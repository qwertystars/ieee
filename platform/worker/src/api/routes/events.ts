import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { disasterEvents, incidents } from '../../db/schema';
import { eq, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const eventRoutes = new Hono<AppEnv>();

const VALID_TYPES = ['flood', 'wildfire', 'cyclone', 'earthquake', 'landslide', 'chemical_spill', 'heatwave', 'power_outage', 'civil_emergency', 'disease_outbreak', 'tsunami', 'tornado', 'avalanche', 'drought', 'building_collapse', 'crowd_crush', 'industrial_fire', 'oil_spill', 'radiological', 'custom'];

eventRoutes.get('/events', async (c) => {
  const orgId = c.get('orgId');
  const limit = parseInt(c.req.query('limit') ?? '50');
  const offset = parseInt(c.req.query('offset') ?? '0');
  const db = drizzle(c.env.db);

  const result = await db.select().from(disasterEvents)
    .where(orgId ? eq(disasterEvents.orgId, orgId) : sql`1=1`)
    .orderBy(desc(disasterEvents.createdAt))
    .limit(limit).offset(offset).all();

  return c.json({ items: result, total: result.length, limit, offset });
});

eventRoutes.get('/events/:id', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(disasterEvents)
    .where(eq(disasterEvents.id, c.req.param('id'))).limit(1).all();
  const event = result[0];
  if (!event) return c.json({ error: { code: 'NOT_FOUND', message: 'Event not found', request_id: c.get('requestId') } }, 404);
  return c.json(event);
});

eventRoutes.post('/events', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const type = body.type as string;
  if (!type || !VALID_TYPES.includes(type)) {
    return c.json({ error: { code: 'INVALID_TYPE', message: `Type must be one of: ${VALID_TYPES.join(', ')}`, request_id: c.get('requestId') } }, 400);
  }

  const orgId = c.get('orgId') ?? 'system';
  const incidentId = body.incidentId as string ?? ulid();
  const id = ulid();
  const db = drizzle(c.env.db);

  if (!body.incidentId) {
    await db.insert(incidents).values({
      id: incidentId, orgId, type, severity: 'moderate', status: 'active',
      title: body.name as string ?? `${type} event`,
      description: body.description as string | null,
      geometry: body.affectedRegion ? JSON.stringify(body.affectedRegion) : null,
      startsAt: nowMs(), createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  await db.insert(disasterEvents).values({
    id, orgId, incidentId,
    name: body.name as string,
    type,
    status: 'active',
    description: body.description as string | null,
    affectedRegion: body.affectedRegion ? JSON.stringify(body.affectedRegion) : null,
    startsAt: body.startsAt as number | null ?? nowMs(),
    expectedEnd: body.expectedEnd as number | null,
    createdBy: c.get('orgId') ?? 'system',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId, actor: c.get('orgId') ?? 'system', action: 'event.create', entity: `event:${id}`, after: body });
  return c.json({ id, incidentId, type, name: body.name, status: 'active' }, 201);
});

eventRoutes.patch('/events/:id', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const existing = await db.select().from(disasterEvents)
    .where(eq(disasterEvents.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Event not found', request_id: c.get('requestId') } }, 404);

  const updates: Record<string, unknown> = { updatedAt: nowMs() };
  if (body.name) updates.name = body.name;
  if (body.status) updates.status = body.status;
  if (body.description !== undefined) updates.description = body.description;
  if (body.expectedEnd !== undefined) updates.expectedEnd = body.expectedEnd;

  await db.update(disasterEvents).set(updates).where(eq(disasterEvents.id, c.req.param('id')));
  await writeAudit({ db, orgId: existing[0].orgId, incidentId: existing[0].incidentId, actor: c.get('orgId') ?? 'system', action: 'event.update', entity: `event:${c.req.param('id')}`, before: existing[0], after: body });
  return c.json({ ok: true, id: c.req.param('id') });
});
