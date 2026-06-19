import type { MiddlewareHandler } from 'hono';
import type { AppEnv } from './requestId';
import { drizzle } from 'drizzle-orm/d1';
import { apiKeys } from '../db/schema';
import { eq } from 'drizzle-orm';
import { sha256 } from '../lib/audit';

export function requireApiKey(requiredScopes: string[]): MiddlewareHandler<AppEnv> {
  return async (c, next) => {
    const authHeader = c.req.header('Authorization') ?? '';
    if (!authHeader.startsWith('Bearer sk_live_')) {
      return c.json({ error: { code: 'UNAUTHENTICATED', message: 'API key required', request_id: c.get('requestId') } }, 401);
    }

    const fullKey = authHeader.slice(7);
    const prefix = fullKey.slice(0, 8);
    const keyHash = await sha256(fullKey);

    const db = drizzle(c.env.db);
    const result = await db
      .select()
      .from(apiKeys)
      .where(eq(apiKeys.prefix, prefix))
      .limit(1)
      .all();

    const apiKey = result[0];
    if (!apiKey || apiKey.revokedAt !== null) {
      return c.json({ error: { code: 'INVALID_KEY', message: 'Invalid or revoked API key', request_id: c.get('requestId') } }, 401);
    }

    if (apiKey.hash !== keyHash) {
      return c.json({ error: { code: 'INVALID_KEY', message: 'Invalid API key', request_id: c.get('requestId') } }, 401);
    }

    const hasAllScopes = requiredScopes.every((s) => apiKey.scopes?.includes(s) || apiKey.scopes?.includes('*'));
    if (!hasAllScopes) {
      return c.json({ error: { code: 'INSUFFICIENT_SCOPE', message: `Required scopes: ${requiredScopes.join(', ')}`, request_id: c.get('requestId') } }, 403);
    }

    c.set('orgId', apiKey.orgId);
    await next();
  };
}
