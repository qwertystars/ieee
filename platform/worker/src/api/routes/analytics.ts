import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { analyticsRollups, decisions, savedSearches, kbDocuments, incidents, tasks, shelters, alerts } from '../../db/schema';
import { eq, and, desc, sql, count } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { sha256 } from '../../lib/audit';

export const analyticsRoutes = new Hono<AppEnv>();

// T135: Write analytics rollup
analyticsRoutes.post('/analytics/rollup', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(analyticsRollups).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    metricName: body.metricName as string,
    metricValue: (body.metricValue as number) ?? 0,
    dimensions: (body.dimensions as Record<string, unknown>) ?? {},
    period: ((body.period as string) ?? 'daily') as 'hourly' | 'daily' | 'weekly',
    rolledAt: nowMs(),
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T135: Get analytics dashboard
analyticsRoutes.get('/analytics/dashboard', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const rollups = await db.select().from(analyticsRollups)
    .where(orgId ? eq(analyticsRollups.orgId, orgId) : sql`1=1`)
    .orderBy(desc(analyticsRollups.rolledAt)).limit(100).all();
  return c.json({ items: rollups });
});

// T137: Create decision (hash-chained)
analyticsRoutes.post('/decisions', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const id = ulid();
  const ts = nowMs();

  const lastDecision = await db.select({ hash: decisions.hash })
    .from(decisions).where(eq(decisions.orgId, orgId))
    .orderBy(desc(decisions.createdAt)).limit(1).all();
  const prevHash = lastDecision[0]?.hash ?? '0000000000000000000000000000000000000000000000000000000000000000';

  const payload = JSON.stringify({ id, orgId, engine: body.engine, title: body.title, ts, prevHash });
  const hash = await sha256(payload);

  await db.insert(decisions).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    engine: body.engine as string,
    title: body.title as string,
    recommendation: (body.recommendation as string) ?? null,
    confidence: (body.confidence as number) ?? 0.5,
    citations: (body.citations as string[]) ?? [],
    riskScore: (body.riskScore as number) ?? null,
    impactEstimate: (body.impactEstimate as number) ?? null,
    status: 'draft',
    prevHash,
    hash,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  return c.json({ id, hash, ok: true, status: 'draft' }, 201);
});

// T137: Approve decision (human-only)
analyticsRoutes.post('/decisions/:id/approve', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  await db.update(decisions).set({
    status: 'approved',
    approvedBy: orgId,
    approvedAt: nowMs(),
    reviewStatus: 'official',
    updatedAt: nowMs(),
  }).where(eq(decisions.id, c.req.param('id')));
  return c.json({ ok: true, status: 'approved' });
});

// T139: Unified search
analyticsRoutes.get('/search', async (c) => {
  const orgId = c.get('orgId');
  const q = c.req.query('q');
  if (!q) return c.json({ items: [] });
  const db = drizzle(c.env.db);
  const results: { type: string; id: string; title: string }[] = [];

  const incidentResults = await db.select().from(incidents)
    .where(and(
      orgId ? eq(incidents.orgId, orgId) : sql`1=1`,
      sql`title LIKE ${'%' + q + '%'}`,
    )).limit(10).all();
  for (const i of incidentResults) results.push({ type: 'incident', id: i.id, title: i.title });

  const taskResults = await db.select().from(tasks)
    .where(and(
      orgId ? eq(tasks.orgId, orgId) : sql`1=1`,
      sql`title LIKE ${'%' + q + '%'}`,
    )).limit(10).all();
  for (const t of taskResults) results.push({ type: 'task', id: t.id, title: t.title });

  const shelterResults = await db.select().from(shelters)
    .where(and(
      orgId ? eq(shelters.orgId, orgId) : sql`1=1`,
      sql`name LIKE ${'%' + q + '%'}`,
    )).limit(10).all();
  for (const s of shelterResults) results.push({ type: 'shelter', id: s.id, title: s.name });

  return c.json({ items: results });
});

// T139: Save search
analyticsRoutes.post('/search/save', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(savedSearches).values({
    id, orgId,
    userId: (body.userId as string) ?? orgId,
    name: body.name as string,
    query: body.query as string,
    filters: (body.filters as Record<string, unknown>) ?? {},
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T141: KB document CRUD
analyticsRoutes.post('/kb/documents', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(kbDocuments).values({
    id, orgId,
    title: body.title as string,
    contentMd: body.contentMd as string,
    docType: ((body.docType as string) ?? 'general') as 'sop' | 'playbook' | 'law' | 'contact' | 'guide' | 'general',
    version: 1,
    tags: (body.tags as string[]) ?? [],
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

analyticsRoutes.get('/kb/documents', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(kbDocuments)
    .where(orgId ? eq(kbDocuments.orgId, orgId) : sql`1=1`)
    .orderBy(desc(kbDocuments.updatedAt)).all();
  return c.json({ items: result });
});

// T135: Incident summary stats
analyticsRoutes.get('/analytics/summary', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const incidentCount = await db.select({ count: count() }).from(incidents).where(orgId ? eq(incidents.orgId, orgId) : sql`1=1`).all();
  const taskCount = await db.select({ count: count() }).from(tasks).where(orgId ? eq(tasks.orgId, orgId) : sql`1=1`).all();
  const shelterCount = await db.select({ count: count() }).from(shelters).where(orgId ? eq(shelters.orgId, orgId) : sql`1=1`).all();
  const alertCount = await db.select({ count: count() }).from(alerts).where(orgId ? eq(alerts.orgId, orgId) : sql`1=1`).all();

  return c.json({
    incidents: incidentCount[0]?.count ?? 0,
    tasks: taskCount[0]?.count ?? 0,
    shelters: shelterCount[0]?.count ?? 0,
    alerts: alertCount[0]?.count ?? 0,
  });
});
