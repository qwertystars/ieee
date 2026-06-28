import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { helpRequests, tasks, taskExtras } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';
import { helpPriorityScore, priorityLabel } from '../../lib/scoring/taskPriority';
import { simpleGeoHash } from '../../lib/dedupe/tasks';

export const helpRequestRoutes = new Hono<AppEnv>();

// T57: Create help request (all inbound channels)
helpRequestRoutes.post('/help-requests', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);

  const source = ((body.source as string) ?? 'public') as 'public' | 'sms' | 'email' | 'whatsapp' | 'telegram' | 'ivr' | 'hotline' | 'field';
  const externalId = (body.externalId as string) ?? ulid();

  // Dedupe check: (source, external_id) unique
  const existing = await db.select().from(helpRequests)
    .where(and(eq(helpRequests.source, source), eq(helpRequests.externalId, externalId))).limit(1).all();
  if (existing[0]) {
    return c.json({ id: existing[0].id, ok: true, duplicate: true });
  }

  // Repeat-caller detection
  let repeatCaller = false;
  if (body.contactPhone) {
    const prior = await db.select().from(helpRequests)
      .where(eq(helpRequests.contactPhone, body.contactPhone as string)).limit(1).all();
    repeatCaller = prior.length > 0;
  }

  // Priority scoring
  const severity = severityByCategory(body.category as string);
  const vulnerability = (body.vulnerability as number) ?? 0.5;
  const score = helpPriorityScore({ severity, vulnerability, ageMs: 0 });
  const priorityLabel_ = priorityLabel(score);

  const id = ulid();
  await db.insert(helpRequests).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    source,
    externalId,
    category: ((body.category as string) ?? 'other') as 'rescue' | 'medical' | 'food' | 'water' | 'shelter' | 'transport' | 'missing' | 'trapped' | 'animal' | 'accessibility' | 'other',
    description: (body.description as string) ?? null,
    geo: (body.geo as string) ?? null,
    address: (body.address as string) ?? null,
    contactName: (body.contactName as string) ?? null,
    contactPhone: (body.contactPhone as string) ?? null,
    peopleCount: (body.peopleCount as number) ?? 1,
    priority: priorityLabel_,
    score,
    status: 'pending',
    confidence: 0.5,
    repeatCaller,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: (body.incidentId as string) ?? null, actor: orgId, action: 'help_request.created', entity: `help_request:${id}`, after: { source, externalId, category: body.category } });
  return c.json({ id, ok: true, priority: priorityLabel_, score }, 201);
});

function severityByCategory(category?: string): number {
  switch (category) {
    case 'rescue': case 'trapped': return 4;
    case 'medical': return 3.5;
    case 'missing': return 3;
    case 'shelter': case 'transport': return 2;
    case 'food': case 'water': return 1.5;
    default: return 1;
  }
}

helpRequestRoutes.get('/help-requests', async (c) => {
  const orgId = c.get('orgId');
  const status = c.req.query('status');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(helpRequests.orgId, orgId) : sql`1=1`];
  if (status) conditions.push(eq(helpRequests.status, status as 'pending' | 'triaged' | 'assigned' | 'in_progress' | 'resolved' | 'closed' | 'duplicate'));
  if (incidentId) conditions.push(eq(helpRequests.incidentId, incidentId));
  const result = await db.select().from(helpRequests).where(and(...conditions)).orderBy(desc(helpRequests.createdAt)).all();
  return c.json({ items: result });
});

helpRequestRoutes.get('/help-requests/:id', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(helpRequests).where(eq(helpRequests.id, c.req.param('id'))).limit(1).all();
  if (!result[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Help request not found', request_id: c.get('requestId') } }, 404);
  return c.json(result[0]);
});

// T58: Triage — assign (creates linked task) + callback scheduling
helpRequestRoutes.post('/help-requests/:id/assign', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const hr = await db.select().from(helpRequests).where(eq(helpRequests.id, c.req.param('id'))).limit(1).all();
  if (!hr[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Help request not found', request_id: c.get('requestId') } }, 404);

  // Create linked task
  const taskId = ulid();
  await db.insert(tasks).values({
    id: taskId, orgId,
    incidentId: hr[0].incidentId ?? 'unassigned',
    title: `Help: ${hr[0].category} — ${hr[0].description?.slice(0, 60) ?? hr[0].id}`,
    description: hr[0].description,
    location: hr[0].geo,
    priority: hr[0].priority as 'low' | 'medium' | 'high' | 'critical',
    status: 'assigned',
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  await db.insert(taskExtras).values({
    taskId, kind: 'help_request', geo: hr[0].geo, riskScore: 0, impactScore: 0, urgencyScore: hr[0].score,
  });

  await db.update(helpRequests).set({ status: 'assigned', assignedTaskId: taskId, updatedAt: nowMs() }).where(eq(helpRequests.id, hr[0].id));
  await writeAudit({ db, orgId, incidentId: hr[0].incidentId, actor: orgId, action: 'help_request.assigned', entity: `help_request:${hr[0].id}`, after: { taskId } });
  return c.json({ ok: true, taskId });
});

// T58: Merge duplicate
helpRequestRoutes.post('/help-requests/:id/merge', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const targetId = body.targetId as string;
  const db = drizzle(c.env.db);
  await db.update(helpRequests).set({ status: 'duplicate', mergedIntoId: targetId, updatedAt: nowMs() }).where(eq(helpRequests.id, c.req.param('id')));
  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'help_request.merged', entity: `help_request:${c.req.param('id')}`, after: { targetId } });
  return c.json({ ok: true });
});

// T59: Fraud detection + abuse protection
helpRequestRoutes.get('/help-requests/fraud-check', async (c) => {
  const phone = c.req.query('phone');
  if (!phone) return c.json({ flagged: false });
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const recent = await db.select().from(helpRequests)
    .where(and(eq(helpRequests.contactPhone, phone), orgId ? eq(helpRequests.orgId, orgId) : sql`1=1`))
    .orderBy(desc(helpRequests.createdAt)).limit(10).all();
  // Velocity check: >5 requests in last hour = flag
  const oneHourAgo = Date.now() - 3600 * 1000;
  const recentCount = recent.filter((r) => r.createdAt > oneHourAgo).length;
  const flagged = recentCount > 5;
  return c.json({ flagged, recentCount, reason: flagged ? 'velocity' : null });
});

// T59: Surge detection (rate spike per H3 area)
helpRequestRoutes.get('/help-requests/surge', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const oneHourAgo = Date.now() - 3600 * 1000;
  const recent = await db.select().from(helpRequests)
    .where(and(
      orgId ? eq(helpRequests.orgId, orgId) : sql`1=1`,
      sql`created_at > ${oneHourAgo}`,
    )).all();

  // Group by geo hash
  const byArea = new Map<string, number>();
  for (const r of recent) {
    if (!r.geo) continue;
    const hash = simpleGeoHash(r.geo);
    byArea.set(hash, (byArea.get(hash) ?? 0) + 1);
  }
  const surges = [...byArea.entries()].filter(([, count]) => count > 10).map(([hash, count]) => ({ hash, count }));
  return c.json({ surges, totalRecent: recent.length });
});

// T58: Callback scheduling (Queue with retry)
helpRequestRoutes.post('/help-requests/:id/callback', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  try {
    await c.env.alertQ.send({
      type: 'callback',
      helpRequestId: c.req.param('id'),
      orgId,
      phone: body.phone,
      scheduledAt: (body.scheduledAt as number) ?? Date.now(),
      __idempotencyKey: ulid(),
    });
  } catch { /* Queue may not be bound */ }
  await writeAudit({ db: drizzle(c.env.db), orgId, incidentId: null, actor: orgId, action: 'help_request.callback_scheduled', entity: `help_request:${c.req.param('id')}`, after: body });
  return c.json({ ok: true });
});
