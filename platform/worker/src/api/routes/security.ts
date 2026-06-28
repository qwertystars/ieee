import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { securityLogs, retentionPolicies, consents, featureFlags, announcements, dsrRequests, complianceRecords } from '../../db/schema';
import { eq, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const securityRoutes = new Hono<AppEnv>();

// T143: Log security action
securityRoutes.post('/security/logs', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(securityLogs).values({
    id, orgId,
    action: body.action as string,
    actor: (body.actor as string) ?? orgId,
    entityType: (body.entityType as string) ?? null,
    entityId: (body.entityId as string) ?? null,
    ipAddr: (body.ipAddr as string) ?? null,
    userAgent: (body.userAgent as string) ?? null,
    details: (body.details as Record<string, unknown>) ?? {},
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T145: Set retention policy
securityRoutes.post('/retention/policies', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(retentionPolicies).values({
    id, orgId,
    dataClass: body.dataClass as string,
    ttlDays: (body.ttlDays as number) ?? 365,
    legalHold: (body.legalHold as boolean) ?? false,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T146: Record consent
securityRoutes.post('/consents', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(consents).values({
    id, orgId,
    personRef: body.personRef as string,
    purpose: body.purpose as string,
    granted: (body.granted as boolean) ?? true,
    grantedAt: nowMs(),
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T146: Revoke consent
securityRoutes.post('/consents/:id/revoke', async (c) => {
  const db = drizzle(c.env.db);
  await db.update(consents).set({ granted: false, revokedAt: nowMs() }).where(eq(consents.id, c.req.param('id')));
  return c.json({ ok: true });
});

// T148: Feature flags
securityRoutes.post('/feature-flags', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(featureFlags).values({
    id, orgId,
    key: body.key as string,
    enabled: (body.enabled as boolean) ?? false,
    scope: ((body.scope as string) ?? 'org') as 'global' | 'org' | 'incident',
    incidentId: (body.incidentId as string) ?? null,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

securityRoutes.get('/feature-flags', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(featureFlags).where(orgId ? eq(featureFlags.orgId, orgId) : sql`1=1`).all();
  return c.json({ items: result });
});

// T148: Announcements
securityRoutes.post('/announcements', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(announcements).values({
    id, orgId,
    message: body.message as string,
    level: ((body.level as string) ?? 'info') as 'info' | 'warning' | 'critical',
    active: true,
    dismissible: (body.dismissible as boolean) ?? true,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T147: DSR request
securityRoutes.post('/dsr', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(dsrRequests).values({
    id, orgId,
    personRef: body.personRef as string,
    requestType: body.requestType as 'export' | 'delete' | 'rectify',
    status: 'pending',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  try {
    await c.env.aiQ.send({
      type: 'dsr_process',
      dsrId: id,
      orgId,
      personRef: body.personRef,
      requestType: body.requestType,
      __idempotencyKey: ulid(),
    });
  } catch { /* Queue may not be bound */ }

  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'dsr.created', entity: `dsr:${id}`, after: body });
  return c.json({ id, ok: true, status: 'pending' }, 201);
});

// T147: Compliance record
securityRoutes.post('/compliance/records', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(complianceRecords).values({
    id, orgId,
    recordType: body.recordType as string,
    data: (body.data as Record<string, unknown>) ?? {},
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T144: Break-glass access (time-boxed)
securityRoutes.post('/security/break-glass', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const id = ulid();
  const duration = (body.durationMinutes as number) ?? 30;
  const expiry = nowMs() + duration * 60 * 1000;

  await db.insert(securityLogs).values({
    id, orgId,
    action: 'break_glass_activated',
    actor: (body.actor as string) ?? orgId,
    details: { duration, expiry, reason: body.reason },
    createdAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'security.break_glass', entity: `break_glass:${id}`, after: { expiry, reason: body.reason } });
  return c.json({ ok: true, token: ulid(), expiresAt: expiry });
});
