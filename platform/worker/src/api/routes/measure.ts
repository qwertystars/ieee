import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';

export const measureRoutes = new Hono<AppEnv>();

measureRoutes.post('/distance', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown[]>));
  const coords = body.coordinates as Array<[number, number]> | undefined;
  if (!coords || coords.length < 2) return c.json({ error: { code: 'INSUFFICIENT_POINTS', message: 'At least 2 coordinates required', request_id: c.get('requestId') } }, 400);

  let total = 0;
  for (let i = 1; i < coords.length; i++) {
    total += haversine(coords[i - 1]!, coords[i]!);
  }
  return c.json({ distance: total, unit: 'meters' });
});

measureRoutes.post('/area', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown[]>));
  const coords = body.coordinates as Array<[number, number]> | undefined;
  if (!coords || coords.length < 3) return c.json({ error: { code: 'INSUFFICIENT_POINTS', message: 'At least 3 coordinates required', request_id: c.get('requestId') } }, 400);

  const area = polygonArea(coords);
  return c.json({ area, unit: 'square_meters' });
});

function haversine(a: [number, number], b: [number, number]): number {
  const R = 6371000;
  const dLat = ((b[0] - a[0]) * Math.PI) / 180;
  const dLng = ((b[1] - a[1]) * Math.PI) / 180;
  const lat1 = (a[0] * Math.PI) / 180;
  const lat2 = (b[0] * Math.PI) / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function polygonArea(coords: Array<[number, number]>): number {
  let area = 0;
  const R = 6378137;
  for (let i = 0; i < coords.length; i++) {
    const j = (i + 1) % coords.length;
    const lat1 = (coords[i]![0] * Math.PI) / 180;
    const lat2 = (coords[j]![0] * Math.PI) / 180;
    const lng1 = (coords[i]![1] * Math.PI) / 180;
    const lng2 = (coords[j]![1] * Math.PI) / 180;
    area += (lng2 - lng1) * (2 + Math.sin(lat1) + Math.sin(lat2));
  }
  return Math.abs((area * R * R) / 2);
}
