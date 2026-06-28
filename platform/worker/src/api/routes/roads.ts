import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { roadStatuses } from '../../db/schema';
import { eq, desc, and, sql } from 'drizzle-orm';
import { nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const roadRoutes = new Hono<AppEnv>();

const VALID_STATUSES = ['open', 'blocked', 'partially_blocked', 'unknown', 'dangerous'];

roadRoutes.get('/events/:incidentId/roads/status', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(roadStatuses)
    .where(and(
      eq(roadStatuses.incidentId, c.req.param('incidentId')),
      orgId ? eq(roadStatuses.orgId, orgId) : sql`1=1`,
    ))
    .orderBy(desc(roadStatuses.updatedAt)).all();
  return c.json({ items: result });
});

roadRoutes.patch('/roads/:id/status', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const status = body.status as string;
  if (!status || !VALID_STATUSES.includes(status)) {
    return c.json({ error: { code: 'INVALID_STATUS', message: `Status must be one of: ${VALID_STATUSES.join(', ')}`, request_id: c.get('requestId') } }, 422);
  }

  const db = drizzle(c.env.db);
  const existing = await db.select().from(roadStatuses)
    .where(eq(roadStatuses.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Road not found', request_id: c.get('requestId') } }, 404);

  const confidenceScore = body.confidenceScore as number ?? existing[0].confidenceScore;
  await db.update(roadStatuses).set({
    status: status as 'open' | 'blocked' | 'partially_blocked' | 'unknown' | 'dangerous',
    reason: body.reason as string ?? existing[0].reason,
    confidenceScore,
    updatedAt: nowMs(),
  }).where(eq(roadStatuses.id, c.req.param('id')));

  await writeAudit({
    db, orgId: existing[0].orgId, incidentId: existing[0].incidentId,
    actor: c.get('orgId') ?? 'system',
    action: 'road.status_changed',
    entity: `road:${c.req.param('id')}`,
    before: { status: existing[0].status },
    after: { status, confidenceScore },
  });

  return c.json({ ok: true, id: c.req.param('id'), status, confidenceScore });
});
