import type { MiddlewareHandler } from 'hono';
import type { AppEnv } from './requestId';

// FEATURES.md:37 — org_id resolved from auth, never trusted from client body.
// Full impl in T8 (auth): reads from JWT/session. Dev: reads X-Org-Id header.
export function orgContext(): MiddlewareHandler<AppEnv> {
  return async (c, next) => {
    const orgId = c.req.header('X-Org-Id') ?? null;
    c.set('orgId', orgId);
    await next();
  };
}
