import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { agencies, mous, incidentShares, exercises, watches, recoveryCases, costCodes, costEntries, rateCards } from '../../db/schema';
import { eq, and, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const multiagencyRoutes = new Hono<AppEnv>();

// T156: Register agency
multiagencyRoutes.post('/agencies', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(agencies).values({
    id, orgId,
    name: body.name as string,
    capabilities: (body.capabilities as string[]) ?? [],
    coverageArea: (body.coverageArea as string) ?? null,
    contactName: (body.contactName as string) ?? null,
    contactPhone: (body.contactPhone as string) ?? null,
    status: 'active',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T156: Create MOU
multiagencyRoutes.post('/mous', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(mous).values({
    id, orgId,
    agencyId: body.agencyId as string,
    scope: body.scope as string,
    expiry: (body.expiry as number) ?? null,
    docR2Key: (body.docR2Key as string) ?? null,
    status: 'active',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T156: Share incident with another org
multiagencyRoutes.post('/incident-shares', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(incidentShares).values({
    id, orgId,
    incidentId: body.incidentId as string,
    targetOrgId: body.targetOrgId as string,
    scope: (body.scope as string[]) ?? ['read'],
    status: 'pending',
    createdAt: nowMs(),
  });
  await writeAudit({ db, orgId, incidentId: body.incidentId as string, actor: orgId, action: 'incident.shared', entity: `incident_share:${id}`, after: body });
  return c.json({ id, ok: true }, 201);
});

// T158: Create exercise (drill)
multiagencyRoutes.post('/exercises', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(exercises).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    name: body.name as string,
    exerciseMode: ((body.exerciseMode as string) ?? 'tabletop') as 'tabletop' | 'functional' | 'full_scale',
    exerciseActive: (body.exerciseActive as boolean) ?? false,
    startTime: (body.startTime as number) ?? null,
    endTime: (body.endTime as number) ?? null,
    status: 'planned',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T159: Create watch
multiagencyRoutes.post('/watches', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(watches).values({
    id, orgId,
    hazard: body.hazard as string,
    geometry: (body.geometry as string) ?? null,
    state: ((body.state as string) ?? 'monitoring') as 'monitoring' | 'advisory' | 'watch' | 'warning',
    thresholdRule: (body.thresholdRule as string) ?? null,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T160: Create recovery case
multiagencyRoutes.post('/recovery-cases', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(recoveryCases).values({
    id, orgId,
    incidentId: body.incidentId as string,
    householdRef: (body.householdRef as string) ?? null,
    caseworkerId: (body.caseworkerId as string) ?? null,
    stage: 'intake',
    needs: (body.needs as string[]) ?? [],
    cvaAmount: (body.cvaAmount as number) ?? null,
    cvaStatus: 'none',
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T161: Create cost code
multiagencyRoutes.post('/cost-codes', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(costCodes).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    code: body.code as string,
    description: (body.description as string) ?? null,
    femaCategory: (body.femaCategory as string) as 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' ?? null,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T161: Create cost entry
multiagencyRoutes.post('/cost-entries', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(costEntries).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    costCodeId: body.costCodeId as string,
    amount: (body.amount as number) ?? 0,
    currency: (body.currency as string) ?? 'USD',
    source: body.source as 'time' | 'equipment' | 'purchase' | 'contract',
    description: (body.description as string) ?? null,
    ics214Ref: (body.ics214Ref as string) ?? null,
    rateCardId: (body.rateCardId as string) ?? null,
    hours: (body.hours as number) ?? null,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T161: Create rate card
multiagencyRoutes.post('/rate-cards', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(rateCards).values({
    id, orgId,
    role: body.role as string,
    hourlyRate: (body.hourlyRate as number) ?? 0,
    currency: (body.currency as string) ?? 'USD',
    effectiveAt: (body.effectiveAt as number) ?? nowMs(),
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T161: Get burn-rate dashboard
multiagencyRoutes.get('/finance/burn-rate', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(costEntries.orgId, orgId) : sql`1=1`];
  if (incidentId) conditions.push(eq(costEntries.incidentId, incidentId));
  const entries = await db.select().from(costEntries).where(and(...conditions)).all();
  const totalCost = entries.reduce((s, e) => s + e.amount, 0);
  const bySource = entries.reduce((acc, e) => {
    acc[e.source] = (acc[e.source] ?? 0) + e.amount;
    return acc;
  }, {} as Record<string, number>);
  return c.json({ totalCost, entryCount: entries.length, bySource });
});
