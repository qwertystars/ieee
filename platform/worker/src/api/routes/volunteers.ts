import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { responders, volunteerProfiles, communityOrgs, fieldCheckins } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const volunteerRoutes = new Hono<AppEnv>();

// T60: Register volunteer (extends responder with kind=volunteer)
volunteerRoutes.post('/volunteers', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const responderId = ulid();
  const profileId = ulid();
  const db = drizzle(c.env.db);

  await db.insert(responders).values({
    id: responderId, orgId,
    incidentId: (body.incidentId as string) ?? null,
    name: body.name as string,
    kind: 'volunteer',
    status: 'available',
    skills: (body.skills as string[]) ?? [],
    contactPhone: (body.contactPhone as string) ?? null,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await db.insert(volunteerProfiles).values({
    id: profileId, orgId,
    responderId,
    verificationStatus: 'pending',
    trainingStatus: 'not_started',
    backgroundStatus: 'pending',
    insuranceFlag: (body.insuranceFlag as boolean) ?? false,
    safetyBriefingCompleted: false,
    totalHours: 0,
    orgAffiliation: (body.orgAffiliation as string) ?? null,
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'volunteer.registered', entity: `volunteer:${responderId}`, after: body });
  return c.json({ id: responderId, profileId, ok: true }, 201);
});

volunteerRoutes.get('/volunteers', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(responders)
    .where(and(eq(responders.kind, 'volunteer'), orgId ? eq(responders.orgId, orgId) : sql`1=1`)).all();
  return c.json({ items: result });
});

// T60: Verify volunteer
volunteerRoutes.post('/volunteers/:id/verify', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  await db.update(volunteerProfiles).set({
    verificationStatus: 'verified',
    updatedAt: nowMs(),
  }).where(eq(volunteerProfiles.responderId, c.req.param('id')));
  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'volunteer.verified', entity: `volunteer:${c.req.param('id')}`, after: { status: 'verified' } });
  return c.json({ ok: true });
});

// T60: Geofenced check-in (location within site polygon)
volunteerRoutes.post('/volunteers/:id/geofence-checkin', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const responderId = c.req.param('id');
  const db = drizzle(c.env.db);

  // Simple geofence check: if sitePolygon provided, check point-in-polygon
  const sitePolygon = body.sitePolygon as { type: string; coordinates: number[][][] } | undefined;
  const location = body.location as { type: string; coordinates: [number, number] } | undefined;

  if (sitePolygon && location) {
    const [lng, lat] = location.coordinates;
    const ring = sitePolygon.coordinates[0];
    if (ring) {
      const inside = pointInPolygon([lng, lat], ring);
      if (!inside) {
        return c.json({ error: { code: 'OUTSIDE_GEOFENCE', message: 'Check-in location is outside the site polygon', request_id: c.get('requestId') } }, 403);
      }
    }
  }

  const id = ulid();
  await db.insert(fieldCheckins).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? 'unassigned',
    responderId,
    type: 'check_in',
    location: JSON.stringify(location),
    timestamp: nowMs(),
    createdAt: nowMs(),
  });
  await db.update(responders).set({ status: 'on_scene', updatedAt: nowMs() }).where(eq(responders.id, responderId));
  return c.json({ id, ok: true }, 201);
});

// Ray-casting point-in-polygon
function pointInPolygon(point: [number, number], polygon: number[][]): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i]?.[0] ?? 0;
    const yi = polygon[i]?.[1] ?? 0;
    const xj = polygon[j]?.[0] ?? 0;
    const yj = polygon[j]?.[1] ?? 0;
    const intersect = ((yi > y) !== (yj > y)) && (x < ((xj - xi) * (y - yi)) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

// T61: Training quiz (scored form)
volunteerRoutes.post('/volunteers/:id/quiz', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const score = (body.score as number) ?? 0;
  const passed = score >= 0.7;
  await db.update(volunteerProfiles).set({
    trainingStatus: passed ? 'completed' : 'in_progress',
    quizScore: score,
    updatedAt: nowMs(),
  }).where(eq(volunteerProfiles.responderId, c.req.param('id')));
  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'volunteer.quiz', entity: `volunteer:${c.req.param('id')}`, after: { score, passed } });
  return c.json({ score, passed });
});

// T61: Hours tracking (check-in/out diff)
volunteerRoutes.get('/volunteers/:id/hours', async (c) => {
  const db = drizzle(c.env.db);
  const checkins = await db.select().from(fieldCheckins)
    .where(eq(fieldCheckins.responderId, c.req.param('id'))).orderBy(desc(fieldCheckins.timestamp)).all();

  let totalMs = 0;
  let checkInTime: number | null = null;
  for (const c of checkins) {
    if (c.type === 'check_out' && checkInTime !== null) {
      totalMs += c.timestamp - checkInTime;
      checkInTime = null;
    } else if (c.type === 'check_in') {
      checkInTime = c.timestamp;
    }
  }
  const totalHours = totalMs / (3600 * 1000);
  await db.update(volunteerProfiles).set({ totalHours, updatedAt: nowMs() }).where(eq(volunteerProfiles.responderId, c.req.param('id')));
  return c.json({ totalHours });
});

// T62: Community org registry
volunteerRoutes.post('/community-orgs', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(communityOrgs).values({
    id, orgId,
    name: body.name as string,
    type: ((body.type as string) ?? 'ngo') as 'ngo' | 'community' | 'faith' | 'mutual_aid' | 'government' | 'private',
    capabilities: (body.capabilities as string[]) ?? [],
    contactName: (body.contactName as string) ?? null,
    contactPhone: (body.contactPhone as string) ?? null,
    coverageArea: (body.coverageArea as string) ?? null,
    status: 'active',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

volunteerRoutes.get('/community-orgs', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(communityOrgs).where(orgId ? eq(communityOrgs.orgId, orgId) : sql`1=1`).all();
  return c.json({ items: result });
});
