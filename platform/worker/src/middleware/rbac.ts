import type { MiddlewareHandler } from 'hono';
import type { AppEnv } from './requestId';
import { drizzle } from 'drizzle-orm/d1';
import { can } from '../auth/policy';
import { writeAudit } from '../lib/audit';

export function requirePermission(action: string, subject: string): MiddlewareHandler<AppEnv> {
  return async (c, next) => {
    const orgId = c.get('orgId');
    const requestId = c.get('requestId');

    if (!orgId) {
      return c.json({ error: { code: 'UNAUTHENTICATED', message: 'Authentication required', request_id: requestId } }, 401);
    }

    const userId = orgId as string;
    const db = drizzle(c.env.db);
    const allowed = await can(db, orgId, userId, action, subject);

    if (!allowed) {
      await writeAudit({ db, orgId, actor: userId, action: `denied:${action}`, entity: subject, after: { path: c.req.path } });
      return c.json({ error: { code: 'FORBIDDEN', message: `Permission denied: ${action} on ${subject}`, request_id: requestId } }, 403);
    }

    await next();
  };
}
