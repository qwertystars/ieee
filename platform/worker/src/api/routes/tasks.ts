import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { tasks } from '../../db/schema';
import { eq, desc, and, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const taskRoutes = new Hono<AppEnv>();

const VALID_TRANSITIONS: Record<string, string[]> = {
  assigned: ['accepted', 'cancelled'],
  accepted: ['en_route', 'cancelled'],
  en_route: ['on_site', 'cancelled'],
  on_site: ['completed', 'blocked'],
  blocked: ['on_site', 'cancelled'],
  completed: [],
  cancelled: [],
};

taskRoutes.get('/events/:incidentId/tasks', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(tasks)
    .where(and(
      eq(tasks.incidentId, c.req.param('incidentId')),
      orgId ? eq(tasks.orgId, orgId) : sql`1=1`,
    ))
    .orderBy(desc(tasks.createdAt)).all();
  return c.json({ items: result });
});

taskRoutes.post('/events/:incidentId/tasks', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const incidentId = c.req.param('incidentId');
  const id = ulid();
  const db = drizzle(c.env.db);

  await db.insert(tasks).values({
    id, orgId, incidentId,
    recommendationId: body.recommendationId as string | null,
    assignedTeamId: body.assignedTeamId as string | null,
    title: body.title as string,
    description: body.description as string | null,
    location: body.location ? JSON.stringify(body.location) : null,
    priority: ((body.priority as string) ?? 'medium') as 'low' | 'medium' | 'high' | 'critical',
    status: 'assigned',
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId, actor: c.get('orgId') ?? 'system', action: 'task.assigned', entity: `task:${id}`, after: body });
  return c.json({ id, status: 'assigned' }, 201);
});

taskRoutes.patch('/tasks/:id', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const existing = await db.select().from(tasks)
    .where(eq(tasks.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Task not found', request_id: c.get('requestId') } }, 404);

  const newStatus = body.status as string | undefined;
  if (newStatus) {
    const currentStatus = existing[0].status;
    const allowed = VALID_TRANSITIONS[currentStatus] ?? [];
    if (!allowed.includes(newStatus)) {
      return c.json({ error: { code: 'INVALID_TRANSITION', message: 'Invalid task status transition', request_id: c.get('requestId') } }, 409);
    }
  }

  const updates: Record<string, unknown> = { updatedAt: nowMs() };
  if (newStatus) updates.status = newStatus;
  if (body.assignedTeamId !== undefined) updates.assignedTeamId = body.assignedTeamId;
  if (body.title !== undefined) updates.title = body.title;
  if (body.description !== undefined) updates.description = body.description;
  if (body.priority !== undefined) updates.priority = body.priority;

  await db.update(tasks).set(updates).where(eq(tasks.id, c.req.param('id')));

  await writeAudit({
    db, orgId: existing[0].orgId, incidentId: existing[0].incidentId,
    actor: c.get('orgId') ?? 'system',
    action: 'task.status_changed',
    entity: `task:${c.req.param('id')}`,
    before: { status: existing[0].status },
    after: updates,
  });

  return c.json({ ok: true, id: c.req.param('id'), status: newStatus ?? existing[0].status });
});
