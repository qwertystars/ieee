import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { responders, vehicles, equipment, shifts, fieldCheckins, fieldReports } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const fieldRoutes = new Hono<AppEnv>();

// T53: Responder registries CRUD
fieldRoutes.post('/responders', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(responders).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    userId: (body.userId as string) ?? null,
    name: body.name as string,
    kind: ((body.kind as string) ?? 'responder') as 'responder' | 'volunteer' | 'medical' | 'k9',
    status: 'available',
    skills: (body.skills as string[]) ?? [],
    certifications: (body.certifications as { name: string; expiry: number | null; docKey: string | null }[]) ?? [],
    contactPhone: (body.contactPhone as string) ?? null,
    currentLocation: (body.currentLocation as string) ?? null,
    teamId: (body.teamId as string) ?? null,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  await writeAudit({ db, orgId, incidentId: (body.incidentId as string) ?? null, actor: orgId, action: 'responder.created', entity: `responder:${id}`, after: body });
  return c.json({ id, ok: true }, 201);
});

fieldRoutes.get('/responders', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(responders)
    .where(orgId ? eq(responders.orgId, orgId) : sql`1=1`).all();
  return c.json({ items: result });
});

fieldRoutes.get('/responders/:id', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(responders).where(eq(responders.id, c.req.param('id'))).limit(1).all();
  if (!result[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Responder not found', request_id: c.get('requestId') } }, 404);
  return c.json(result[0]);
});

fieldRoutes.patch('/responders/:id', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const updates: Record<string, unknown> = { updatedAt: nowMs() };
  if (body.status) updates.status = body.status;
  if (body.currentLocation) updates.currentLocation = body.currentLocation;
  if (body.skills) updates.skills = body.skills;
  if (body.teamId !== undefined) updates.teamId = body.teamId;
  await db.update(responders).set(updates).where(eq(responders.id, c.req.param('id')));
  return c.json({ ok: true });
});

// T53: Live location update (watchPosition → IncidentRoom DO via DO fetch)
fieldRoutes.post('/responders/:id/location', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const location = body.location as string;
  await db.update(responders).set({ currentLocation: location, updatedAt: nowMs() }).where(eq(responders.id, c.req.param('id')));

  // Also broadcast to IncidentRoom DO if incidentId present
  const responder = await db.select().from(responders).where(eq(responders.id, c.req.param('id'))).limit(1).all();
  if (responder[0]?.incidentId) {
    try {
      const doId = c.env.IncidentRoom.idFromName(responder[0].incidentId);
      const stub = c.env.IncidentRoom.get(doId);
      await stub.fetch(new Request(`https://do/location`, {
        method: 'POST',
        body: JSON.stringify({ responderId: responder[0].id, location, timestamp: Date.now() }),
      }));
    } catch { /* DO may not be available in all envs */ }
  }

  await writeAudit({ db, orgId, incidentId: responder[0]?.incidentId ?? null, actor: orgId, action: 'responder.location_update', entity: `responder:${c.req.param('id')}`, after: { location } });
  return c.json({ ok: true });
});

// T54: Check-in/out (ICS-211)
fieldRoutes.post('/responders/:id/check-in', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const responderId = c.req.param('id');
  const id = ulid();
  const db = drizzle(c.env.db);
  const responder = await db.select().from(responders).where(eq(responders.id, responderId)).limit(1).all();
  if (!responder[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Responder not found', request_id: c.get('requestId') } }, 404);

  await db.insert(fieldCheckins).values({
    id, orgId,
    incidentId: responder[0].incidentId ?? (body.incidentId as string),
    responderId,
    type: 'check_in',
    location: (body.location as string) ?? null,
    shiftId: (body.shiftId as string) ?? null,
    timestamp: nowMs(),
    createdAt: nowMs(),
  });
  await db.update(responders).set({ status: 'on_scene', updatedAt: nowMs() }).where(eq(responders.id, responderId));
  await writeAudit({ db, orgId, incidentId: responder[0].incidentId ?? null, actor: orgId, action: 'responder.check_in', entity: `responder:${responderId}`, after: body });
  return c.json({ id, ok: true }, 201);
});

fieldRoutes.post('/responders/:id/check-out', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const responderId = c.req.param('id');
  const id = ulid();
  const db = drizzle(c.env.db);
  const responder = await db.select().from(responders).where(eq(responders.id, responderId)).limit(1).all();
  if (!responder[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Responder not found', request_id: c.get('requestId') } }, 404);

  await db.insert(fieldCheckins).values({
    id, orgId,
    incidentId: responder[0].incidentId ?? (body.incidentId as string),
    responderId,
    type: 'check_out',
    location: (body.location as string) ?? null,
    shiftId: (body.shiftId as string) ?? null,
    timestamp: nowMs(),
    createdAt: nowMs(),
  });
  await db.update(responders).set({ status: 'off_duty', updatedAt: nowMs() }).where(eq(responders.id, responderId));
  return c.json({ id, ok: true }, 201);
});

// T54: Shift assignment + handoff + fatigue (hours since check-in)
fieldRoutes.post('/shifts', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(shifts).values({
    id, orgId,
    incidentId: body.incidentId as string,
    responderId: body.responderId as string,
    teamId: (body.teamId as string) ?? null,
    role: (body.role as string) ?? null,
    startTime: (body.startTime as number) ?? nowMs(),
    endTime: (body.endTime as number) ?? null,
    buddyId: (body.buddyId as string) ?? null,
    status: 'active',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

fieldRoutes.get('/responders/:id/fatigue', async (c) => {
  const db = drizzle(c.env.db);
  const checkins = await db.select().from(fieldCheckins)
    .where(eq(fieldCheckins.responderId, c.req.param('id'))).orderBy(desc(fieldCheckins.timestamp)).limit(1).all();
  if (!checkins[0] || checkins[0].type !== 'check_in') return c.json({ fatigueHours: 0, onDuty: false });
  const hoursOnDuty = (Date.now() - checkins[0].timestamp) / (3600 * 1000);
  return c.json({ fatigueHours: hoursOnDuty, onDuty: true, threshold: 12 });
});

// T54: Mayday/panic (priority WS broadcast + SMS fallback via Queue)
fieldRoutes.post('/responders/:id/mayday', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const responder = await db.select().from(responders).where(eq(responders.id, c.req.param('id'))).limit(1).all();
  if (!responder[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Responder not found', request_id: c.get('requestId') } }, 404);

  // Broadcast to IncidentRoom DO
  if (responder[0].incidentId) {
    try {
      const doId = c.env.IncidentRoom.idFromName(responder[0].incidentId);
      const stub = c.env.IncidentRoom.get(doId);
      await stub.fetch(new Request('https://do/mayday', {
        method: 'POST',
        body: JSON.stringify({ responderId: responder[0].id, location: responder[0].currentLocation, timestamp: Date.now() }),
      }));
    } catch { /* DO may not be available */ }
  }

  // Enqueue SMS fallback via alertQ
  try {
    await c.env.alertQ.send({
      type: 'mayday',
      responderId: responder[0].id,
      orgId,
      incidentId: responder[0].incidentId,
      location: responder[0].currentLocation,
      timestamp: Date.now(),
      __idempotencyKey: ulid(),
    });
  } catch { /* Queue may not be bound */ }

  await writeAudit({ db, orgId, incidentId: responder[0].incidentId ?? null, actor: orgId, action: 'responder.mayday', entity: `responder:${responder[0].id}`, after: body });
  return c.json({ ok: true, mayday: true });
});

// T55: Field report submission (Form Builder forms)
fieldRoutes.post('/field-reports', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(fieldReports).values({
    id, orgId,
    incidentId: body.incidentId as string,
    responderId: body.responderId as string,
    formType: body.formType as 'checklist' | 'triage' | 'damage' | 'trapped' | 'road_blockage' | 'infrastructure' | 'dosimeter' | 'k9' | 'par',
    taskId: (body.taskId as string) ?? null,
    data: body.data as Record<string, unknown>,
    attachments: (body.attachments as string[]) ?? null,
    location: (body.location as string) ?? null,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  await writeAudit({ db, orgId, incidentId: body.incidentId as string, actor: orgId, action: 'field_report.created', entity: `field_report:${id}`, after: body });
  return c.json({ id, ok: true }, 201);
});

fieldRoutes.get('/field-reports', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(fieldReports.orgId, orgId) : sql`1=1`];
  if (incidentId) conditions.push(eq(fieldReports.incidentId, incidentId));
  const result = await db.select().from(fieldReports).where(and(...conditions)).orderBy(desc(fieldReports.createdAt)).all();
  return c.json({ items: result });
});

// T56: Equipment checkout
fieldRoutes.post('/equipment/:id/checkout', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  await db.update(equipment).set({
    status: 'checked_out',
    checkedOutBy: body.responderId as string,
    checkedOutAt: nowMs(),
    updatedAt: nowMs(),
  }).where(eq(equipment.id, c.req.param('id')));
  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'equipment.checkout', entity: `equipment:${c.req.param('id')}`, after: body });
  return c.json({ ok: true });
});

fieldRoutes.post('/equipment/:id/return', async (c) => {
  const db = drizzle(c.env.db);
  await db.update(equipment).set({
    status: 'available',
    checkedOutBy: null,
    checkedOutAt: null,
    updatedAt: nowMs(),
  }).where(eq(equipment.id, c.req.param('id')));
  return c.json({ ok: true });
});

// T56: PAR (Personnel Accountability Report)
fieldRoutes.get('/incidents/:incidentId/par', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const onDuty = await db.select().from(responders)
    .where(and(
      eq(responders.incidentId, c.req.param('incidentId')),
      orgId ? eq(responders.orgId, orgId) : sql`1=1`,
      eq(responders.status, 'on_scene'),
    )).all();
  return c.json({ totalAccounted: onDuty.length, responders: onDuty.map((r) => ({ id: r.id, name: r.name })) });
});

// Vehicles CRUD
fieldRoutes.post('/vehicles', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(vehicles).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    name: body.name as string,
    type: (body.type as string) ?? 'truck',
    capacity: (body.capacity as number) ?? 4,
    status: 'available',
    teamId: (body.teamId as string) ?? null,
    fuelLevel: (body.fuelLevel as number) ?? 100,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

fieldRoutes.get('/vehicles', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(vehicles).where(orgId ? eq(vehicles.orgId, orgId) : sql`1=1`).all();
  return c.json({ items: result });
});
