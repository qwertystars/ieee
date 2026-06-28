import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';

export const geocodeRoutes = new Hono<AppEnv>();

geocodeRoutes.get('/search', async (c) => {
  const q = c.req.query('q') ?? '';
  if (!q) return c.json({ error: { code: 'MISSING_QUERY', message: 'Query required', request_id: c.get('requestId') } }, 400);

  const latLngMatch = q.match(/^(-?\d+\.?\d*),\s*(-?\d+\.?\d*)$/);
  if (latLngMatch) {
    return c.json({ type: 'latlng', lat: parseFloat(latLngMatch[1]!), lng: parseFloat(latLngMatch[2]!) });
  }

  const cached = await c.env.cache.get(`geocode:${q}`);
  if (cached) return c.json(JSON.parse(cached));

  try {
    const resp = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=5`, {
      headers: { 'User-Agent': 'disaster-response-platform/1.0' },
    });
    const data = await resp.json() as Array<{ lat: string; lon: string; display_name: string }>;
    const results = data.map((d) => ({ lat: parseFloat(d.lat), lng: parseFloat(d.lon), name: d.display_name }));
    await c.env.cache.put(`geocode:${q}`, JSON.stringify(results), { expirationTtl: 3600 });
    return c.json({ type: 'address', results });
  } catch {
    return c.json({ type: 'address', results: [], error: 'Geocoder unavailable' });
  }
});

geocodeRoutes.get('/reverse', async (c) => {
  const lat = c.req.query('lat');
  const lng = c.req.query('lng');
  if (!lat || !lng) return c.json({ error: { code: 'MISSING_PARAMS', message: 'lat and lng required', request_id: c.get('requestId') } }, 400);

  const cached = await c.env.cache.get(`reverse:${lat},${lng}`);
  if (cached) return c.json(JSON.parse(cached));

  try {
    const resp = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`, {
      headers: { 'User-Agent': 'disaster-response-platform/1.0' },
    });
    const data = await resp.json() as { display_name: string };
    const result = { lat: parseFloat(lat), lng: parseFloat(lng), name: data.display_name };
    await c.env.cache.put(`reverse:${lat},${lng}`, JSON.stringify(result), { expirationTtl: 3600 });
    return c.json(result);
  } catch {
    return c.json({ lat: parseFloat(lat), lng: parseFloat(lng), name: 'Unknown', error: 'Reverse geocoder unavailable' });
  }
});

geocodeRoutes.get('/mgrs', async (c) => {
  const mgrs = c.req.query('code') ?? '';
  return c.json({ type: 'mgrs', code: mgrs, note: 'MGRS conversion requires mgrs npm package' });
});
