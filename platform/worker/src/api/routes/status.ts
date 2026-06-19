import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';

export const statusRoutes = new Hono<AppEnv>();

statusRoutes.get('/', async (c) => {
  const cached = await c.env.cache.get('status:public');
  if (cached) return c.json(JSON.parse(cached));

  const status = { ok: true, environment: c.env.ENVIRONMENT, timestamp: Date.now() };
  await c.env.cache.put('status:public', JSON.stringify(status), { expirationTtl: 60 });
  return c.json(status);
});

statusRoutes.get('/internal', async (c) => {
  return c.json({ ok: true, environment: c.env.ENVIRONMENT, bindings: { db: !!c.env.db, media: !!c.env.media, metrics: !!c.env.metrics } });
});
