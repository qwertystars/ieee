import type { MiddlewareHandler } from 'hono';
import type { Env } from '../index';

export type AppEnv = {
  Bindings: Env;
  Variables: { requestId: string; orgId: string | null; incidentId: string | null };
};

export function requestId(): MiddlewareHandler<AppEnv> {
  return async (c, next) => {
    const headerId = c.req.header('X-Request-Id');
    const id = headerId ?? crypto.randomUUID();
    c.set('requestId', id);
    c.header('X-Request-Id', id);
    await next();
  };
}
