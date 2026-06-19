import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { incidents, incidentNotes, mapZones } from '../../db/schema';
import { eq, and, desc } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';

export const commandRoutes = new Hono<AppEnv>();

const PANELS = [
  'overview', 'current_threat', 'population_impact', 'evacuation', 'shelter',
  'resource', 'field_team', 'weather', 'infrastructure', 'communications',
  'road_access', 'medical_needs', 'timeline', 'open_task', 'critical_alerts',
  'decision_log', 'pinned_priorities', 'cross_incident',
];

commandRoutes.get('/:id/panels', async (c) => {
  return c.json({ panels: PANELS });
});

commandRoutes.get('/:id/panels/:panel', async (c) => {
  const panel = c.req.param('panel');
  if (!PANELS.includes(panel)) return c.json({ error: { code: 'INVALID_PANEL', message: `Unknown panel: ${panel}`, request_id: c.get('requestId') } }, 400);

  const db = drizzle(c.env.db);
  const inc = await db.select().from(incidents).where(eq(incidents.id, c.req.param('id'))).limit(1).all();
  if (!inc[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Incident not found', request_id: c.get('requestId') } }, 404);

  const notes = await db.select().from(incidentNotes).where(eq(incidentNotes.incidentId, c.req.param('id'))).orderBy(desc(incidentNotes.createdAt)).limit(10).all();
  const zones = await db.select().from(mapZones).where(eq(mapZones.incidentId, c.req.param('id'))).limit(20).all();

  return c.json({ panel, incident: inc[0], data: { notes, zonesCount: zones.length } });
});

commandRoutes.get('/:id/decision-log', async (c) => {
  const db = drizzle(c.env.db);
  const decisions = await db.select().from(incidentNotes)
    .where(and(eq(incidentNotes.incidentId, c.req.param('id')), eq(incidentNotes.authorId, 'decision_log')))
    .orderBy(desc(incidentNotes.createdAt)).limit(50).all();
  return c.json({ items: decisions });
});

commandRoutes.post('/:id/decision-log', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: 'decision_log', body: body.decision ?? '', createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});

commandRoutes.get('/:id/pinned-priorities', async (c) => {
  const db = drizzle(c.env.db);
  const priorities = await db.select().from(incidentNotes)
    .where(and(eq(incidentNotes.incidentId, c.req.param('id')), eq(incidentNotes.authorId, 'pinned_priority')))
    .orderBy(desc(incidentNotes.createdAt)).limit(10).all();
  return c.json({ items: priorities });
});

commandRoutes.post('/:id/pinned-priorities', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: 'pinned_priority', body: body.priority ?? '', createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});
