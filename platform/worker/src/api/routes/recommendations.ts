import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { recommendations } from '../../db/schema';
import { eq, desc, and, sql } from 'drizzle-orm';
import { nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const recommendationRoutes = new Hono<AppEnv>();

recommendationRoutes.get('/events/:incidentId/recommendations', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(recommendations)
    .where(and(
      eq(recommendations.incidentId, c.req.param('incidentId')),
      orgId ? eq(recommendations.orgId, orgId) : sql`1=1`,
    ))
    .orderBy(desc(recommendations.createdAt)).all();
  return c.json({ items: result });
});

recommendationRoutes.post('/events/:incidentId/recommendations/:id/approve', async (c) => {
  const db = drizzle(c.env.db);
  const existing = await db.select().from(recommendations)
    .where(eq(recommendations.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Recommendation not found', request_id: c.get('requestId') } }, 404);

  await db.update(recommendations).set({
    status: 'approved',
    updatedAt: nowMs(),
  }).where(eq(recommendations.id, c.req.param('id')));

  await writeAudit({
    db, orgId: existing[0].orgId, incidentId: existing[0].incidentId,
    actor: c.get('orgId') ?? 'system',
    action: 'recommendation.approved',
    entity: `recommendation:${c.req.param('id')}`,
    before: { status: existing[0].status },
    after: { status: 'approved' },
  });

  return c.json({ ok: true, id: c.req.param('id'), status: 'approved' });
});

recommendationRoutes.post('/events/:incidentId/recommendations/:id/dismiss', async (c) => {
  const db = drizzle(c.env.db);
  const existing = await db.select().from(recommendations)
    .where(eq(recommendations.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Recommendation not found', request_id: c.get('requestId') } }, 404);

  await db.update(recommendations).set({
    status: 'dismissed',
    updatedAt: nowMs(),
  }).where(eq(recommendations.id, c.req.param('id')));

  await writeAudit({
    db, orgId: existing[0].orgId, incidentId: existing[0].incidentId,
    actor: c.get('orgId') ?? 'system',
    action: 'recommendation.dismissed',
    entity: `recommendation:${c.req.param('id')}`,
    before: { status: existing[0].status },
    after: { status: 'dismissed' },
  });

  return c.json({ ok: true, id: c.req.param('id'), status: 'dismissed' });
});
