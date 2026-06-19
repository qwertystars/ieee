import type { ErrorHandler } from 'hono';
import type { AppEnv } from './requestId';
import { structuredLog } from './logger';

export const errorHandler: ErrorHandler<AppEnv> = (err, c) => {
  const reqId = c.get('requestId') ?? crypto.randomUUID();
  const orgId = c.get('orgId') ?? null;

  structuredLog('error', 'unhandled_error', {
    requestId: reqId,
    orgId,
    error: err.message,
    stack: err.stack,
    path: c.req.path,
    method: c.req.method,
  });

  return c.json(
    {
      error: {
        code: 'INTERNAL_ERROR',
        message: err.message,
        request_id: reqId,
      },
    },
    500,
  );
};
