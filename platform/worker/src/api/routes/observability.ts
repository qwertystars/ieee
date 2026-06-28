import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { sloMetrics, cronJobs, localeDocuments, glossaryTerms } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';

export const observabilityRoutes = new Hono<AppEnv>();

// T163: Record SLO metric
observabilityRoutes.post('/slo/metrics', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(sloMetrics).values({
    id, orgId,
    metricName: body.metricName as string,
    p50: (body.p50 as number) ?? null,
    p95: (body.p95 as number) ?? null,
    p99: (body.p99 as number) ?? null,
    errorRate: (body.errorRate as number) ?? null,
    requestCount: (body.requestCount as number) ?? null,
    period: (body.period as string) ?? 'hourly',
    measuredAt: (body.measuredAt as number) ?? nowMs(),
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T163: Get SLO dashboard
observabilityRoutes.get('/slo/dashboard', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const metrics = await db.select().from(sloMetrics)
    .where(orgId ? eq(sloMetrics.orgId, orgId) : sql`1=1`)
    .orderBy(desc(sloMetrics.measuredAt)).limit(50).all();
  const avgP95 = metrics.length > 0 ? metrics.reduce((s, m) => s + (m.p95 ?? 0), 0) / metrics.length : 0;
  const avgErrorRate = metrics.length > 0 ? metrics.reduce((s, m) => s + (m.errorRate ?? 0), 0) / metrics.length : 0;
  return c.json({ metrics, avgP95: Math.round(avgP95), avgErrorRate: Math.round(avgErrorRate * 10000) / 100 });
});

// T165: Register cron job
observabilityRoutes.post('/cron/jobs', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(cronJobs).values({
    id, orgId,
    name: body.name as string,
    schedule: body.schedule as string,
    active: true,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T165: List cron jobs
observabilityRoutes.get('/cron/jobs', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(cronJobs).where(orgId ? eq(cronJobs.orgId, orgId) : sql`1=1`).all();
  return c.json({ items: result });
});

// T169: Create locale document
observabilityRoutes.post('/i18n/locales', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(localeDocuments).values({
    id, orgId,
    locale: body.locale as string,
    namespace: body.namespace as string,
    content: (body.content as Record<string, unknown>) ?? {},
    version: 1,
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T169: Get locale
observabilityRoutes.get('/i18n/locales/:locale', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(localeDocuments)
    .where(and(
      eq(localeDocuments.locale, c.req.param('locale')),
      orgId ? eq(localeDocuments.orgId, orgId) : sql`1=1`,
    )).all();
  return c.json({ items: result });
});

// T169: Glossary term (locked translations)
observabilityRoutes.post('/i18n/glossary', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(glossaryTerms).values({
    id, orgId,
    term: body.term as string,
    translations: (body.translations as Record<string, string>) ?? {},
    locked: (body.locked as boolean) ?? false,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});
