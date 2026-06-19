import { Hono } from 'hono';
import type { Env } from './index';

export function createApp() {
  const app = new Hono<{
    Bindings: Env;
    Variables: { requestId: string; orgId: string | null; incidentId: string | null };
  }>();

  app.route('/api', new Hono());
  app.route('/api/auth', new Hono());
  app.route('/api/orgs', new Hono());
  app.route('/api/incidents', new Hono());
  app.route('/api/admin', new Hono());

  return app;
}
