import type { MiddlewareHandler } from 'hono';
import type { AppEnv } from './requestId';

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

function structuredLog(
  level: LogLevel,
  msg: string,
  fields: Record<string, unknown>,
): void {
  const entry = {
    ts: Date.now(),
    level,
    request_id: fields.requestId ?? null,
    org_id: fields.orgId ?? null,
    incident_id: fields.incidentId ?? null,
    msg,
    ...fields,
  };
  const line = JSON.stringify(entry);
  if (level === 'error') console.error(line);
  else if (level === 'warn') console.warn(line);
  else console.log(line);
}

export function logger(): MiddlewareHandler<AppEnv> {
  return async (c, next) => {
    const start = Date.now();
    const reqId = c.get('requestId') ?? '-';
    const orgId = c.get('orgId') ?? null;

    structuredLog('info', 'request.start', {
      requestId: reqId,
      orgId,
      method: c.req.method,
      path: c.req.path,
    });

    await next();

    const duration = Date.now() - start;
    structuredLog('info', 'request.end', {
      requestId: reqId,
      orgId,
      method: c.req.method,
      path: c.req.path,
      status: c.res.status,
      durationMs: duration,
    });
  };
}

export { structuredLog };
