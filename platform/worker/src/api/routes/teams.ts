import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { responseTeams } from '../../db/schema';
import { eq, desc, and, sql } from 'drizzle-orm';
import { nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const teamRoutes = new Hono<AppEnv>();

const VALID_TEAM_STATUSES = ['available', 'dispatched', 'on_scene', 'off_duty', 'standby'];

teamRoutes.get('/events/:incidentId/teams', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(responseTeams)
    .where(and(
      eq(responseTeams.incidentId, c.req.param('incidentId')),
      orgId ? eq(responseTeams.orgId, orgId) : sql`1=1`,
    ))
    .orderBy(desc(responseTeams.updatedAt)).all();
  return c.json({ items: result });
});

teamRoutes.patch('/teams/:id/location', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const existing = await db.select().from(responseTeams)
    .where(eq(responseTeams.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Team not found', request_id: c.get('requestId') } }, 404);

  await db.update(responseTeams).set({
    currentLocation: body.location ? JSON.stringify(body.location) : existing[0].currentLocation,
    updatedAt: nowMs(),
  }).where(eq(responseTeams.id, c.req.param('id')));

  await writeAudit({
    db, orgId: existing[0].orgId, incidentId: existing[0].incidentId,
    actor: c.get('orgId') ?? 'system',
    action: 'team.location_updated',
    entity: `team:${c.req.param('id')}`,
    before: { location: existing[0].currentLocation },
    after: { location: body.location },
  });

  return c.json({ ok: true, id: c.req.param('id') });
});

teamRoutes.patch('/teams/:id/status', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const status = body.status as string;
  if (!status || !VALID_TEAM_STATUSES.includes(status)) {
    return c.json({ error: { code: 'INVALID_STATUS', message: `Status must be one of: ${VALID_TEAM_STATUSES.join(', ')}`, request_id: c.get('requestId') } }, 422);
  }

  const db = drizzle(c.env.db);
  const existing = await db.select().from(responseTeams)
    .where(eq(responseTeams.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Team not found', request_id: c.get('requestId') } }, 404);

  await db.update(responseTeams).set({
    status: status as 'available' | 'dispatched' | 'on_scene' | 'off_duty' | 'standby',
    updatedAt: nowMs(),
  }).where(eq(responseTeams.id, c.req.param('id')));

  await writeAudit({
    db, orgId: existing[0].orgId, incidentId: existing[0].incidentId,
    actor: c.get('orgId') ?? 'system',
    action: 'team.status_changed',
    entity: `team:${c.req.param('id')}`,
    before: { status: existing[0].status },
    after: { status },
  });

  return c.json({ ok: true, id: c.req.param('id'), status });
});
