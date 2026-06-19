import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { settings } from '../../db/schema';
import { eq, and } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const settingsRoutes = new Hono<AppEnv>();

settingsRoutes.get('/:orgId', async (c) => {
  const orgId = c.req.param('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(settings).where(eq(settings.orgId, orgId)).all();
  const map: Record<string, unknown> = {};
  for (const s of result) { map[s.key] = s.value; }
  return c.json({ orgId, settings: map });
});

settingsRoutes.put('/:orgId/:key', async (c) => {
  const orgId = c.req.param('orgId');
  const key = c.req.param('key');
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const value = body.value;

  const db = drizzle(c.env.db);
  const existing = await db.select().from(settings)
    .where(and(eq(settings.orgId, orgId), eq(settings.key, key)))
    .limit(1).all();

  if (existing[0]) {
    await db.update(settings).set({ value: JSON.stringify(value), updatedAt: nowMs() })
      .where(eq(settings.id, existing[0].id));
  } else {
    await db.insert(settings).values({
      id: ulid(), scope: 'org', orgId, key,
      value: JSON.stringify(value), createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  await writeAudit({ db, orgId, actor: c.get('orgId') ?? 'system', action: 'settings.update', entity: `setting:${key}`, after: value });
  return c.json({ ok: true, key, value });
});
