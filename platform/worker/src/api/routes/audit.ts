import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { events } from '../../db/schema';
import { eq, desc, and } from 'drizzle-orm';
import { nowMs } from '../../lib/ulid';
import { verifyChain } from '../../lib/audit';

export const auditRoutes = new Hono<AppEnv>();

auditRoutes.get('/:orgId', async (c) => {
  const db = drizzle(c.env.db);
  const limit = parseInt(c.req.query('limit') ?? '50');
  const result = await db.select().from(events)
    .where(eq(events.orgId, c.req.param('orgId')))
    .orderBy(desc(events.ts)).limit(limit).all();
  return c.json({ items: result });
});

auditRoutes.get('/:orgId/verify', async (c) => {
  const db = drizzle(c.env.db);
  const result = await verifyChain(db, c.req.param('orgId'));
  return c.json(result);
});

auditRoutes.get('/:orgId/timeline/:entity', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(events)
    .where(and(eq(events.orgId, c.req.param('orgId')), eq(events.entity, c.req.param('entity'))))
    .orderBy(desc(events.ts)).limit(100).all();
  return c.json({ items: result });
});

auditRoutes.post('/:orgId/export', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(events)
    .where(eq(events.orgId, c.req.param('orgId')))
    .orderBy(desc(events.ts)).all();
  const json = JSON.stringify(result, null, 2);
  const key = `exports/${c.req.param('orgId')}/audit-${nowMs()}.json`;
  await c.env.exports.put(key, json, { customMetadata: { orgId: c.req.param('orgId'), type: 'audit-export' } });
  return c.json({ url: `/api/audit/${c.req.param('orgId')}/download/${key}`, key });
});

auditRoutes.get('/:orgId/download/:key{.*}', async (c) => {
  const key = c.req.param('key');
  const obj = await c.env.exports.get(key);
  if (!obj) return c.json({ error: { code: 'NOT_FOUND', message: 'Export not found', request_id: c.get('requestId') } }, 404);
  return new Response(obj.body, { headers: { 'Content-Type': 'application/json', 'Content-Disposition': `attachment; filename="${key.split('/').pop()}"` } });
});
