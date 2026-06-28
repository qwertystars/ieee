import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { shelters } from '../../db/schema';
import { eq, desc, and, sql } from 'drizzle-orm';
import { nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const shelterRoutes = new Hono<AppEnv>();

const VALID_SHELTER_STATUSES = ['open', 'closed', 'full', 'preparing'];

shelterRoutes.get('/events/:incidentId/shelters', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(shelters)
    .where(and(
      eq(shelters.incidentId, c.req.param('incidentId')),
      orgId ? eq(shelters.orgId, orgId) : sql`1=1`,
    ))
    .orderBy(desc(shelters.updatedAt)).all();
  return c.json({ items: result });
});

shelterRoutes.patch('/shelters/:id/status', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const status = body.status as string;
  if (!status || !VALID_SHELTER_STATUSES.includes(status)) {
    return c.json({ error: { code: 'INVALID_STATUS', message: `Status must be one of: ${VALID_SHELTER_STATUSES.join(', ')}`, request_id: c.get('requestId') } }, 422);
  }

  const db = drizzle(c.env.db);
  const existing = await db.select().from(shelters)
    .where(eq(shelters.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Shelter not found', request_id: c.get('requestId') } }, 404);

  const updates: Record<string, unknown> = { status, updatedAt: nowMs() };
  if (body.currentOccupancy !== undefined) updates.currentOccupancy = body.currentOccupancy;
  if (body.totalCapacity !== undefined) updates.totalCapacity = body.totalCapacity;

  await db.update(shelters).set(updates).where(eq(shelters.id, c.req.param('id')));

  await writeAudit({
    db, orgId: existing[0].orgId, incidentId: existing[0].incidentId,
    actor: c.get('orgId') ?? 'system',
    action: 'shelter.status_changed',
    entity: `shelter:${c.req.param('id')}`,
    before: { status: existing[0].status },
    after: updates,
  });

  return c.json({ ok: true, id: c.req.param('id'), status });
});
