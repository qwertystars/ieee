function parseCookie(header: string, name: string): string | undefined { const m = header.match(new RegExp(name + "=([^;]+)")); return m?.[1]; }
import type { MiddlewareHandler } from 'hono';
import type { AppEnv } from './requestId';
import { drizzle } from 'drizzle-orm/d1';
import { sessions } from '../db/schema';
import { eq } from 'drizzle-orm';
import { sha256 } from '../lib/audit';
import { nowMs } from '../lib/ulid';

export function requireAuth(): MiddlewareHandler<AppEnv> {
  return async (c, next) => {
    const token = c.req.header('Authorization')?.replace('Bearer ', '') ?? parseCookie(c.req.header('Cookie') ?? '', 'session') ?? '';
    if (!token) {
      return c.json({ error: { code: 'UNAUTHENTICATED', message: 'Authentication required', request_id: c.get('requestId') } }, 401);
    }

    const tokenHash = await sha256(token);
    const db = drizzle(c.env.db);
    const now = nowMs();

    const result = await db
      .select()
      .from(sessions)
      .where(eq(sessions.tokenHash, tokenHash))
      .limit(1)
      .all();

    const session = result[0];
    if (!session || session.expiresAt < now) {
      return c.json({ error: { code: 'INVALID_SESSION', message: 'Session expired or invalid', request_id: c.get('requestId') } }, 401);
    }

    c.set('orgId', session.userId);
    await next();
  };
}
