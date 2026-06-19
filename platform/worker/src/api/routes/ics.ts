import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { incidentNotes } from '../../db/schema';
import { eq, and, desc } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';

export const icsRoutes = new Hono<AppEnv>();

const ICS_FORMS = ['ics201', 'ics202', 'ics203', 'ics204', 'ics205', 'ics206', 'ics207', 'ics209', 'ics211', 'ics214'] as const;

icsRoutes.get('/:id/ics', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(incidentNotes)
    .where(and(eq(incidentNotes.incidentId, c.req.param('id')), eq(incidentNotes.authorId, 'ics_form')))
    .orderBy(desc(incidentNotes.createdAt)).all();
  return c.json({ items: result, forms: ICS_FORMS });
});

icsRoutes.post('/:id/ics/:formType', async (c) => {
  const formType = c.req.param('formType');
  if (!ICS_FORMS.includes(formType as typeof ICS_FORMS[number])) {
    return c.json({ error: { code: 'INVALID_FORM', message: `Unknown ICS form: ${formType}`, request_id: c.get('requestId') } }, 400);
  }
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: 'ics_form', body: JSON.stringify({ formType, data: body, reviewStatus: 'draft' }), createdAt: nowMs(),
  });
  return c.json({ id, formType, reviewStatus: 'draft' }, 201);
});

icsRoutes.get('/:id/ics/:formType', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(incidentNotes)
    .where(and(eq(incidentNotes.incidentId, c.req.param('id')), eq(incidentNotes.authorId, 'ics_form')))
    .orderBy(desc(incidentNotes.createdAt)).all();
  const filtered = result.filter((n) => {
    try { return JSON.parse(n.body)?.formType === c.req.param('formType'); } catch { return false; }
  });
  return c.json({ items: filtered });
});

icsRoutes.post('/:id/briefings', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(incidentNotes).values({
    id, orgId: c.get('orgId') ?? 'system', incidentId: c.req.param('id'),
    authorId: 'briefing', body: JSON.stringify(body), createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});
