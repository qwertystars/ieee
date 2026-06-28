import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';

export const mapExportRoutes = new Hono<AppEnv>();

mapExportRoutes.post('/:incidentId/screenshot', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const key = `exports/${c.req.param('incidentId')}/screenshot-${Date.now()}.png`;
  if (body.imageData) {
    const base64 = (body.imageData as string).split(',')[1] ?? '';
    await c.env.exports.put(key, base64Decode(base64), { httpMetadata: { contentType: 'image/png' } });
  }
  return c.json({ key, url: `/api/map-export/${c.req.param('incidentId')}/download/${key}` });
});

mapExportRoutes.post('/:incidentId/print', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const key = `exports/${c.req.param('incidentId')}/print-${Date.now()}.html`;
  const html = `<!DOCTYPE html><html><head><title>Map Export</title></head><body>
  <h1>${body.title ?? 'Map Export'}</h1>
  <p>Scale: ${body.scale ?? '1:25000'}</p>
  <p>Generated: ${new Date().toISOString()}</p>
  </body></html>`;
  await c.env.exports.put(key, html, { httpMetadata: { contentType: 'text/html' } });
  return c.json({ key, format: 'print-layout' });
});

mapExportRoutes.get('/:incidentId/download/:key{.*}', async (c) => {
  const key = c.req.param('key');
  const obj = await c.env.exports.get(key);
  if (!obj) return c.json({ error: { code: 'NOT_FOUND', message: 'Export not found', request_id: c.get('requestId') } }, 404);
  const headers = new Headers();
  obj.writeHttpMetadata(headers);
  return new Response(obj.body, { headers });
});

mapExportRoutes.get('/:incidentId/embed', async (c) => {
  const token = c.req.query('token') ?? '';
  if (token.length < 16) return c.json({ error: { code: 'INVALID_TOKEN', message: 'Embed token required', request_id: c.get('requestId') } }, 403);
  return c.json({ incidentId: c.req.param('incidentId'), mode: 'embed', publicOnly: true });
});

function base64Decode(s: string): ArrayBuffer {
  const bytes = atob(s);
  const buf = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) buf[i] = bytes.charCodeAt(i);
  return buf.buffer;
}
