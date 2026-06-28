import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { incidentReports } from '../../db/schema';
import { eq, desc, and, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const reportRoutes = new Hono<AppEnv>();

const VALID_CATEGORIES = ['flooding', 'trapped_person', 'road_blocked', 'power_outage', 'shelter_need', 'medical_emergency', 'fire', 'structural_damage', 'water_contamination', 'other'];
const VALID_URGENCIES = ['low', 'medium', 'high', 'critical'];

reportRoutes.get('/events/:incidentId/reports', async (c) => {
  const orgId = c.get('orgId');
  const limit = parseInt(c.req.query('limit') ?? '50');
  const offset = parseInt(c.req.query('offset') ?? '0');
  const db = drizzle(c.env.db);

  const result = await db.select().from(incidentReports)
    .where(and(
      eq(incidentReports.incidentId, c.req.param('incidentId')),
      orgId ? eq(incidentReports.orgId, orgId) : sql`1=1`,
    ))
    .orderBy(desc(incidentReports.createdAt))
    .limit(limit).offset(offset).all();

  return c.json({ items: result, total: result.length, limit, offset });
});

reportRoutes.post('/events/:incidentId/reports', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const pathIncidentId = c.req.param('incidentId');
  const bodyIncidentId = body.eventId as string | undefined;

  if (bodyIncidentId && bodyIncidentId !== pathIncidentId) {
    return c.json({ error: { code: 'EVENT_MISMATCH', message: 'Report event_id must match path event_id', request_id: c.get('requestId') } }, 400);
  }

  const geometry = body.geometry;
  if (!geometry || (typeof geometry === 'object' && (geometry as Record<string, unknown>).type !== 'Point')) {
    return c.json({ error: { code: 'INVALID_GEOMETRY', message: 'Point geometry required', request_id: c.get('requestId') } }, 400);
  }

  const category = body.reportCategory as string;
  if (!category || !VALID_CATEGORIES.includes(category)) {
    return c.json({ error: { code: 'INVALID_CATEGORY', message: `Category must be one of: ${VALID_CATEGORIES.join(', ')}`, request_id: c.get('requestId') } }, 400);
  }

  const urgency = ((body.urgency as string) ?? 'medium') as 'low' | 'medium' | 'high' | 'critical';
  if (!VALID_URGENCIES.includes(urgency)) {
    return c.json({ error: { code: 'INVALID_URGENCY', message: `Urgency must be one of: ${VALID_URGENCIES.join(', ')}`, request_id: c.get('requestId') } }, 400);
  }

  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const reporterType = ((body.reporterType as string) ?? 'citizen') as 'citizen' | 'field_responder' | 'sensor' | 'official';
  const confidenceScore = body.confidenceScore as number ?? 0.5;

  await db.insert(incidentReports).values({
    id, orgId, incidentId: pathIncidentId,
    reporterType,
    reportCategory: category,
    description: body.description as string | null,
    geometry: typeof geometry === 'string' ? geometry : JSON.stringify(geometry),
    photoUrl: body.photoUrl as string | null,
    urgency,
    verificationStatus: 'unverified',
    confidenceScore,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: pathIncidentId, actor: c.get('orgId') ?? 'system', action: 'report.create', entity: `report:${id}`, after: body });
  return c.json({ id, incidentId: pathIncidentId, reportCategory: category, verificationStatus: 'unverified', confidenceScore }, 201);
});

reportRoutes.get('/reports/:id', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(incidentReports)
    .where(eq(incidentReports.id, c.req.param('id'))).limit(1).all();
  const report = result[0];
  if (!report) return c.json({ error: { code: 'NOT_FOUND', message: 'Report not found', request_id: c.get('requestId') } }, 404);
  return c.json(report);
});

reportRoutes.patch('/reports/:id/verify', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const existing = await db.select().from(incidentReports)
    .where(eq(incidentReports.id, c.req.param('id'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Report not found', request_id: c.get('requestId') } }, 404);

  const verificationStatus = ((body.verificationStatus as string) ?? 'medium') as 'unverified' | 'low' | 'medium' | 'high';
  const confidenceScore = body.confidenceScore as number ?? existing[0].confidenceScore;

  await db.update(incidentReports).set({
    verificationStatus,
    confidenceScore,
    updatedAt: nowMs(),
  }).where(eq(incidentReports.id, c.req.param('id')));

  await writeAudit({
    db, orgId: existing[0].orgId, incidentId: existing[0].incidentId,
    actor: c.get('orgId') ?? 'system',
    action: 'report.verify',
    entity: `report:${c.req.param('id')}`,
    before: { verificationStatus: existing[0].verificationStatus },
    after: { verificationStatus, confidenceScore },
  });

  return c.json({ ok: true, id: c.req.param('id'), verificationStatus, confidenceScore });
});
