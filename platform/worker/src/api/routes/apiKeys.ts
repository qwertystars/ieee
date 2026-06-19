import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { apiKeys } from '../../db/schema';
import { eq } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { sha256 } from '../../lib/audit';
import { writeAudit } from '../../lib/audit';

export const apiKeysRoutes = new Hono<AppEnv>();

apiKeysRoutes.post('/:orgId/api-keys', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.req.param('orgId');
  const fullKey = `sk_live_${ulid()}${ulid()}`;
  const prefix = fullKey.slice(0, 12);
  const hash = await sha256(fullKey);
  const id = ulid();

  const db = drizzle(c.env.db);
  await db.insert(apiKeys).values({
    id,
    orgId,
    prefix,
    hash,
    scopes: body.scopes as string[] ?? [],
    createdAt: nowMs(),
  });

  await writeAudit({ db, orgId, actor: c.get('orgId') ?? 'system', action: 'apikey.create', entity: `apikey:${id}` });
  return c.json({ id, key: fullKey, prefix }, 201);
});

apiKeysRoutes.get('/:orgId/api-keys', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db
    .select({ id: apiKeys.id, prefix: apiKeys.prefix, scopes: apiKeys.scopes, lastUsedAt: apiKeys.lastUsedAt, createdAt: apiKeys.createdAt, revokedAt: apiKeys.revokedAt })
    .from(apiKeys)
    .where(eq(apiKeys.orgId, c.req.param('orgId')))
    .all();
  return c.json({ items: result });
});

apiKeysRoutes.delete('/:orgId/api-keys/:keyId', async (c) => {
  const db = drizzle(c.env.db);
  await db.update(apiKeys).set({ revokedAt: nowMs() }).where(eq(apiKeys.id, c.req.param('keyId')));
  await writeAudit({ db, orgId: c.req.param('orgId'), actor: c.get('orgId') ?? 'system', action: 'apikey.revoke', entity: `apikey:${c.req.param('keyId')}` });
  return c.json({ ok: true });
});
