import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { notifications } from '../../db/schema';
import { eq, and, isNull, desc } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';

export const notificationRoutes = new Hono<AppEnv>();

notificationRoutes.get('/', async (c) => {
  const userId = c.get('orgId') as string;
  const db = drizzle(c.env.db);
  const result = await db.select().from(notifications)
    .where(eq(notifications.userId, userId))
    .orderBy(desc(notifications.createdAt)).limit(50).all();
  return c.json({ items: result });
});

notificationRoutes.get('/unread', async (c) => {
  const userId = c.get('orgId') as string;
  const db = drizzle(c.env.db);
  const result = await db.select().from(notifications)
    .where(and(eq(notifications.userId, userId), isNull(notifications.readAt)))
    .orderBy(desc(notifications.createdAt)).limit(50).all();
  return c.json({ items: result });
});

notificationRoutes.post('/', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(notifications).values({
    id,
    orgId: c.get('orgId') ?? 'system',
    userId: body.userId as string,
    kind: body.kind as string,
    title: body.title as string,
    body: body.body as string | null,
    payload: body.payload ? JSON.stringify(body.payload) : null,
    createdAt: nowMs(),
  });
  return c.json({ id }, 201);
});

notificationRoutes.post('/:id/read', async (c) => {
  const db = drizzle(c.env.db);
  await db.update(notifications).set({ readAt: nowMs() }).where(eq(notifications.id, c.req.param('id')));
  return c.json({ ok: true });
});

export async function pushNotification(env: { db: D1Database }, orgId: string, userId: string, kind: string, title: string, body?: string): Promise<void> {
  const db = drizzle(env.db);
  await db.insert(notifications).values({
    id: ulid(), orgId, userId, kind, title, body: body ?? null,
    createdAt: nowMs(),
  });
}
