import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { shelters, shelterStatus, shelterCheckins, shelterSupplyRequests, shelterPlans } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const shelterExtRoutes = new Hono<AppEnv>();

// T65: Shelter status snapshot (extended fields)
shelterExtRoutes.post('/shelters/:id/status-snapshot', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(shelterStatus).values({
    id, orgId,
    shelterId: c.req.param('id'),
    generatorFuel: (body.generatorFuel as number) ?? null,
    waterStatus: ((body.waterStatus as string) ?? 'unknown') as 'adequate' | 'limited' | 'critical' | 'unknown',
    foodStatus: ((body.foodStatus as string) ?? 'unknown') as 'adequate' | 'limited' | 'critical' | 'unknown',
    mealCapacityDay: (body.mealCapacityDay as number) ?? null,
    sanitationRatio: (body.sanitationRatio as number) ?? null,
    staffCount: (body.staffCount as number) ?? 0,
    securityPresent: (body.securityPresent as boolean) ?? false,
    petSupport: (body.petSupport as boolean) ?? false,
    accessibilitySupport: (body.accessibilitySupport as boolean) ?? false,
    medicalSupport: (body.medicalSupport as boolean) ?? false,
    notes: (body.notes as string) ?? null,
    recordedAt: nowMs(),
  });
  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'shelter.status_snapshot', entity: `shelter:${c.req.param('id')}`, after: body });
  return c.json({ id, ok: true }, 201);
});

// T66: Shelter check-in with QR + ShelterCounter DO integration
shelterExtRoutes.post('/shelters/:id/check-in', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const shelter = await db.select().from(shelters).where(eq(shelters.id, c.req.param('id'))).limit(1).all();
  if (!shelter[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Shelter not found', request_id: c.get('requestId') } }, 404);

  // Try ShelterCounter DO for capacity check
  let occupancyResult: { ok: boolean; currentOccupancy?: number; available?: number; error?: string } = { ok: true };
  try {
    const doId = c.env.ShelterCounter.idFromName(shelter[0].id);
    const stub = c.env.ShelterCounter.get(doId);
    const resp = await stub.fetch(new Request('https://do/checkin', {
      method: 'POST',
      body: JSON.stringify({ count: 1 }),
    }));
    occupancyResult = await resp.json() as typeof occupancyResult;
    if (!occupancyResult.ok && occupancyResult.error === 'CAPACITY_EXCEEDED') {
      return c.json({ error: { code: 'CAPACITY_EXCEEDED', message: 'Shelter is at full capacity', request_id: c.get('requestId') } }, 409);
    }
  } catch {
    // Fallback to D1 count
    const checkins = await db.select().from(shelterCheckins)
      .where(and(eq(shelterCheckins.shelterId, shelter[0].id), sql`checked_out_at IS NULL`)).all();
    if (checkins.length >= shelter[0].totalCapacity) {
      return c.json({ error: { code: 'CAPACITY_EXCEEDED', message: 'Shelter is at full capacity', request_id: c.get('requestId') } }, 409);
    }
  }

  // Normalize name for matching (split-name)
  const fullName = (body.fullName as string) ?? 'Unknown';
  const fullNameSplit = fullName.toLowerCase().trim().replace(/\s+/g, ' ');

  await db.insert(shelterCheckins).values({
    id, orgId,
    shelterId: shelter[0].id,
    incidentId: shelter[0].incidentId,
    personName: fullName,
    personNameSplit: fullNameSplit,
    bedNumber: (body.bedNumber as string) ?? null,
    familyGroupId: (body.familyGroupId as string) ?? null,
    vulnerable: (body.vulnerable as boolean) ?? false,
    medicalNeeds: (body.medicalNeeds as boolean) ?? false,
    dietaryNeeds: (body.dietaryNeeds as string) ?? null,
    checkedInAt: nowMs(),
    visibility: 'internal',
    reviewStatus: 'draft',
  });

  await writeAudit({ db, orgId, incidentId: shelter[0].incidentId, actor: orgId, action: 'shelter.checkin', entity: `shelter_checkin:${id}`, after: { shelterId: shelter[0].id, fullName } });
  return c.json({ id, ok: true, occupancy: occupancyResult }, 201);
});

// T66: Check-out
shelterExtRoutes.post('/shelters/:id/check-out', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const checkinId = body.checkinId as string;

  await db.update(shelterCheckins).set({ checkedOutAt: nowMs() }).where(eq(shelterCheckins.id, checkinId));

  // Decrement ShelterCounter
  try {
    const doId = c.env.ShelterCounter.idFromName(c.req.param('id'));
    const stub = c.env.ShelterCounter.get(doId);
    await stub.fetch(new Request('https://do/checkout', { method: 'POST', body: JSON.stringify({ count: 1 }) }));
  } catch { /* D1 fallback already updated */ }

  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'shelter.checkout', entity: `shelter_checkin:${checkinId}`, after: {} });
  return c.json({ ok: true });
});

// T66: List check-ins
shelterExtRoutes.get('/shelters/:id/check-ins', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(shelterCheckins)
    .where(and(eq(shelterCheckins.shelterId, c.req.param('id')), orgId ? eq(shelterCheckins.orgId, orgId) : sql`1=1`))
    .orderBy(desc(shelterCheckins.checkedInAt)).all();
  return c.json({ items: result });
});

// T67: Supply request (ICS-213RR trigger)
shelterExtRoutes.post('/shelters/:id/supply-requests', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const shelter = await db.select().from(shelters).where(eq(shelters.id, c.req.param('id'))).limit(1).all();
  if (!shelter[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Shelter not found', request_id: c.get('requestId') } }, 404);

  await db.insert(shelterSupplyRequests).values({
    id, orgId,
    shelterId: shelter[0].id,
    incidentId: shelter[0].incidentId,
    itemType: body.itemType as string,
    quantity: (body.quantity as number) ?? 1,
    urgency: ((body.urgency as string) ?? 'medium') as 'low' | 'medium' | 'high' | 'critical',
    status: 'requested',
    notes: (body.notes as string) ?? null,
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  // Trigger logistics via alertQ
  try {
    await c.env.alertQ.send({
      type: 'shelter_supply_request',
      shelterId: shelter[0].id,
      orgId,
      incidentId: shelter[0].incidentId,
      itemType: body.itemType,
      quantity: body.quantity ?? 1,
      __idempotencyKey: ulid(),
    });
  } catch { /* Queue may not be bound */ }

  await writeAudit({ db, orgId, incidentId: shelter[0].incidentId, actor: orgId, action: 'shelter.supply_request', entity: `supply_request:${id}`, after: body });
  return c.json({ id, ok: true }, 201);
});

// T67: Overcrowding alert
shelterExtRoutes.get('/shelters/:id/overcrowding', async (c) => {
  const db = drizzle(c.env.db);
  const shelter = await db.select().from(shelters).where(eq(shelters.id, c.req.param('id'))).limit(1).all();
  if (!shelter[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Shelter not found', request_id: c.get('requestId') } }, 404);

  const ratio = shelter[0].totalCapacity > 0 ? shelter[0].currentOccupancy / shelter[0].totalCapacity : 0;
  const overcrowded = ratio >= 0.9;
  return c.json({
    overcrowded,
    ratio: Math.round(ratio * 100) / 100,
    currentOccupancy: shelter[0].currentOccupancy,
    totalCapacity: shelter[0].totalCapacity,
    threshold: 0.9,
  });
});

// T68: Shelter recommendation — nearest finder (haversine)
shelterExtRoutes.get('/shelters/nearest', async (c) => {
  const lat = parseFloat(c.req.query('lat') ?? '0');
  const lng = parseFloat(c.req.query('lng') ?? '0');
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const all = await db.select().from(shelters)
    .where(and(
      eq(shelters.status, 'open'),
      orgId ? eq(shelters.orgId, orgId) : sql`1=1`,
    )).all();

  const withDistance = all.map((s) => {
    let dist = Infinity;
    try {
      const geom = JSON.parse(s.geometry ?? '{"coordinates":[0,0]}') as { coordinates: [number, number] };
      const [slng, slat] = geom.coordinates;
      dist = haversineKm(lat, lng, slat, slng);
    } catch { /* ignore parse error */ }
    return { ...s, distanceKm: Math.round(dist * 100) / 100 };
  }).sort((a, b) => a.distanceKm - b.distanceKm);

  return c.json({ items: withDistance.slice(0, 10) });
});

// T69: Shelter planning
shelterExtRoutes.post('/shelter-plans', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(shelterPlans).values({
    id, orgId,
    incidentId: body.incidentId as string,
    shelterId: (body.shelterId as string) ?? null,
    planType: body.planType as 'donation_drop' | 'temporary' | 'mega' | 'micro' | 'special_needs' | 'hospital_overflow',
    name: body.name as string,
    location: (body.location as string) ?? null,
    estimatedCapacity: (body.estimatedCapacity as number) ?? null,
    hospitalId: (body.hospitalId as string) ?? null,
    status: 'planned',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// Haversine distance in km
function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
