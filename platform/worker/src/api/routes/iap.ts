import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { incidentNotes, incidents } from '../../db/schema';
import { eq } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const iapRoutes = new Hono<AppEnv>();

iapRoutes.post('/:id/sitrep', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: 'sitrep', body: body.content ?? '', createdAt: nowMs(),
  });
  await writeAudit({ db, orgId: c.get('orgId') ?? 'system', actor: c.get('orgId') ?? 'system', action: 'sitrep.create', entity: `incident:${c.req.param('id')}`, after: { draft: true } });
  return c.json({ id, reviewStatus: 'draft' }, 201);
});

iapRoutes.post('/:id/sitrep/:noteId/approve', async (c) => {
  const db = drizzle(c.env.db);
  await db.update(incidentNotes).set({ body: '[APPROVED] ' + (await db.select().from(incidentNotes).where(eq(incidentNotes.id, c.req.param('noteId'))).limit(1).all())[0]?.body })
    .where(eq(incidentNotes.id, c.req.param('noteId')));
  return c.json({ ok: true, reviewStatus: 'official' });
});

iapRoutes.post('/:id/op-period', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: 'op_period', body: JSON.stringify(body), createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});

iapRoutes.post('/:id/iap', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: 'iap', body: JSON.stringify({ ics202: body.ics202, ics204: body.ics204 }), createdAt: nowMs(),
  });
  await writeAudit({ db, orgId: c.get('orgId') ?? 'system', actor: c.get('orgId') ?? 'system', action: 'iap.create', entity: `incident:${c.req.param('id')}`, after: body });
  return c.json({ id, forms: ['ICS-202', 'ICS-204'], reviewStatus: 'draft' }, 201);
});

iapRoutes.post('/:id/iap/:noteId/approve', async (c) => {
  const db = drizzle(c.env.db);
  const existing = await db.select().from(incidentNotes).where(eq(incidentNotes.id, c.req.param('noteId'))).limit(1).all();
  if (!existing[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'IAP not found', request_id: c.get('requestId') } }, 404);
  await writeAudit({ db, orgId: c.get('orgId') ?? 'system', actor: c.get('orgId') ?? 'system', action: 'iap.approve', entity: `iap:${c.req.param('noteId')}`, before: { status: 'draft' }, after: { status: 'official' } });
  return c.json({ ok: true, reviewStatus: 'official' });
});

iapRoutes.post('/:id/escalate', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  await db.update(incidents).set({ severity: body.severity ?? 'severe', updatedAt: nowMs() }).where(eq(incidents.id, c.req.param('id')));
  await writeAudit({ db, orgId: c.get('orgId') ?? 'system', actor: c.get('orgId') ?? 'system', action: 'incident.escalate', entity: `incident:${c.req.param('id')}`, after: body });
  return c.json({ ok: true });
});

iapRoutes.post('/:id/shift-handoff', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: 'shift_handoff', body: body.notes ?? '', createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});

iapRoutes.get('/:id/kiosk/:token', async (c) => {
  const token = c.req.param('token');
  if (token.length < 16) return c.json({ error: { code: 'INVALID_TOKEN', message: 'Invalid kiosk token', request_id: c.get('requestId') } }, 403);
  const db = drizzle(c.env.db);
  const inc = await db.select().from(incidents).where(eq(incidents.id, c.req.param('id'))).limit(1).all();
  if (!inc[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Incident not found', request_id: c.get('requestId') } }, 404);
  return c.json({ incident: inc[0], mode: 'kiosk', token });
});
