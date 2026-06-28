import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { tasks, taskExtras, taskLinks, taskComments, taskAttachments, taskTemplates } from '../../db/schema';
import { eq, and, desc } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';
import { taskPriorityScore, priorityLabel, isConflict } from '../../lib/scoring/taskPriority';

export const taskExtRoutes = new Hono<AppEnv>();

// T50: Link task to map/people/teams/shelters/resources
taskExtRoutes.post('/tasks/:id/links', async (c) => {
  const taskId = c.req.param('id');
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  await db.insert(taskLinks).values({
    id, orgId, taskId,
    targetType: body.targetType as string,
    targetId: body.targetId as string,
    createdAt: nowMs(),
  });
  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'task.linked', entity: `task:${taskId}`, after: body });
  return c.json({ id, ok: true }, 201);
});

taskExtRoutes.get('/tasks/:id/links', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(taskLinks).where(eq(taskLinks.taskId, c.req.param('id'))).all();
  return c.json({ items: result });
});

// T50: Comments
taskExtRoutes.post('/tasks/:id/comments', async (c) => {
  const taskId = c.req.param('id');
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(taskComments).values({
    id, orgId, taskId,
    authorId: body.authorId as string,
    body: body.body as string,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

taskExtRoutes.get('/tasks/:id/comments', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(taskComments).where(eq(taskComments.taskId, c.req.param('id'))).orderBy(desc(taskComments.createdAt)).all();
  return c.json({ items: result });
});

// T50: Attachments (R2 presign assumed done client-side; here just record metadata)
taskExtRoutes.post('/tasks/:id/attachments', async (c) => {
  const taskId = c.req.param('id');
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(taskAttachments).values({
    id, orgId, taskId,
    r2Key: body.r2Key as string,
    name: body.name as string,
    kind: (body.kind as string) ?? 'file',
    uploadedBy: body.uploadedBy as string,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T50: Templates — create + spawn
taskExtRoutes.post('/task-templates', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(taskTemplates).values({
    id, orgId,
    name: body.name as string,
    kind: (body.kind as string) ?? 'general',
    title: body.title as string,
    description: body.description as string,
    priority: (body.priority as string) ?? 'medium',
    checklist: body.checklist as { label: string; done: boolean }[] | null,
    recurringCron: body.recurringCron as string | null,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

taskExtRoutes.post('/task-templates/:id/instantiate', async (c) => {
  const templateId = c.req.param('id');
  const body = await c.req.json().catch(() => ({ incidentId: '' } as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const incidentId = body.incidentId as string;
  const db = drizzle(c.env.db);

  const tmpl = await db.select().from(taskTemplates).where(eq(taskTemplates.id, templateId)).limit(1).all();
  if (!tmpl[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Template not found', request_id: c.get('requestId') } }, 404);

  const taskId = ulid();
  await db.insert(tasks).values({
    id: taskId, orgId, incidentId,
    title: tmpl[0].title,
    description: tmpl[0].description,
    priority: tmpl[0].priority as 'low' | 'medium' | 'high' | 'critical',
    status: 'assigned',
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  await db.insert(taskExtras).values({
    taskId, kind: tmpl[0].kind,
    checklist: tmpl[0].checklist,
    riskScore: 0, impactScore: 0, urgencyScore: 0,
    publicVisible: false,
  });
  return c.json({ id: taskId, ok: true }, 201);
});

// T52: Scores + completion proof + verification
taskExtRoutes.post('/tasks/:id/score', async (c) => {
  const taskId = c.req.param('id');
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);

  const score = taskPriorityScore({
    severity: (body.severity as number) ?? 1,
    vulnerability: (body.vulnerability as number) ?? 0.5,
    ageMs: (body.ageMs as number) ?? 0,
    proximityKm: (body.proximityKm as number) ?? null,
  });
  const label = priorityLabel(score);

  await db.update(taskExtras).set({
    riskScore: (body.risk as number) ?? score,
    impactScore: (body.impact as number) ?? score,
    urgencyScore: score,
  }).where(eq(taskExtras.taskId, taskId));

  await db.update(tasks).set({ priority: label, updatedAt: nowMs() }).where(eq(tasks.id, taskId));
  return c.json({ score, priority: label });
});

// T52: Completion proof (attachment + verifier)
taskExtRoutes.post('/tasks/:id/complete', async (c) => {
  const taskId = c.req.param('id');
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);

  if (!body.proofAttachment && !body.proofNote) {
    return c.json({ error: { code: 'PROOF_REQUIRED', message: 'Completion requires proof attachment or note', request_id: c.get('requestId') } }, 400);
  }

  await db.update(taskExtras).set({
    completionProof: { attachment: body.proofAttachment, note: body.proofNote, verifier: body.verifier },
    verifiedBy: (body.verifier as string) ?? orgId,
    verifiedAt: nowMs(),
  }).where(eq(taskExtras.taskId, taskId));

  await db.update(tasks).set({ status: 'completed', updatedAt: nowMs() }).where(eq(tasks.id, taskId));

  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'task.completed', entity: `task:${taskId}`, after: body });
  return c.json({ ok: true, status: 'completed' });
});

// T51: Import tasks (CSV-like JSON array)
taskExtRoutes.post('/tasks/import', async (c) => {
  const body = await c.req.json().catch(() => [] as unknown[]);
  const orgId = c.get('orgId') ?? 'system';
  const items = Array.isArray(body) ? body : [];
  const db = drizzle(c.env.db);
  const inserted: string[] = [];
  const quarantined: unknown[] = [];

  for (const item of items) {
    const r = item as Record<string, unknown>;
    if (!r.title || !r.incidentId) { quarantined.push(r); continue; }
    const id = ulid();
    try {
      await db.insert(tasks).values({
        id, orgId,
        incidentId: r.incidentId as string,
        title: r.title as string,
        description: (r.description as string) ?? null,
        priority: ((r.priority as string) ?? 'medium') as 'low' | 'medium' | 'high' | 'critical',
        status: 'assigned',
        visibility: 'internal',
        reviewStatus: 'draft',
        createdAt: nowMs(), updatedAt: nowMs(),
      });
      inserted.push(id);
    } catch {
      quarantined.push(r);
    }
  }
  return c.json({ inserted: inserted.length, quarantined: quarantined.length, ids: inserted });
});

// T51: Conflict detection
taskExtRoutes.get('/tasks/:id/conflicts', async (c) => {
  const taskId = c.req.param('id');
  const db = drizzle(c.env.db);
  const task = await db.select().from(tasks).where(eq(tasks.id, taskId)).limit(1).all();
  if (!task[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Task not found', request_id: c.get('requestId') } }, 404);

  const extra = await db.select().from(taskExtras).where(eq(taskExtras.taskId, taskId)).limit(1).all();
  const extraRow = extra[0];
  const h3 = extraRow?.h3;
  if (!h3 || !extraRow) return c.json({ conflicts: [] });

  const taskRow = task[0];
  const allTasks = await db.select().from(tasks).where(and(eq(tasks.incidentId, taskRow.incidentId), eq(tasks.orgId, taskRow.orgId))).all();
  const conflictIds = allTasks
    .filter((t) => t.id !== taskId)
    .filter((t) => isConflict([{ h3, kind: extraRow.kind ?? 'general', createdAt: taskRow.createdAt }], { h3, kind: extraRow.kind ?? 'general', createdAt: t.createdAt }))
    .map((t) => t.id);

  return c.json({ conflicts: conflictIds });
});

// T52: Geofence auto-complete (arrival closes "reach X" task)
taskExtRoutes.post('/tasks/:id/geofence-arrive', async (c) => {
  const taskId = c.req.param('id');
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const task = await db.select().from(tasks).where(eq(tasks.id, taskId)).limit(1).all();
  if (!task[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Task not found', request_id: c.get('requestId') } }, 404);

  // Auto-complete on arrival
  await db.update(tasks).set({ status: 'completed', updatedAt: nowMs() }).where(eq(tasks.id, taskId));
  await db.update(taskExtras).set({ verifiedBy: 'geofence', verifiedAt: nowMs() }).where(eq(taskExtras.taskId, taskId));
  await writeAudit({ db, orgId, incidentId: task[0].incidentId, actor: 'geofence', action: 'task.geofence_arrive', entity: `task:${taskId}`, after: { status: 'completed' } });
  return c.json({ ok: true, status: 'completed' });
});
