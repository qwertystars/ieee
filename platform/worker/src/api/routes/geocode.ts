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
  if (!mgrs) return c.json({ error: { code: 'MISSING_CODE', message: 'MGRS code required', request_id: c.get('requestId') } }, 400);

  const result = mgrsToLatLng(mgrs);
  if (!result) return c.json({ error: { code: 'INVALID_MGRS', message: 'Could not parse MGRS code', request_id: c.get('requestId') } }, 400);
  return c.json({ type: 'mgrs', code: mgrs, lat: result.lat, lng: result.lng });
});

const MGRS_RE = /^(\d{1,2})([C-X])([A-Z]{2})(\d+)(\d+)$/;

function mgrsToLatLng(code: string): { lat: number; lng: number } | null {
  const m = code.toUpperCase().trim().match(MGRS_RE);
  if (!m) return null;

  const zone = parseInt(m[1]!, 10);
  const bandLetter = m[2]!;
  const colLetters = m[3]!;
  const easting = parseInt(m[4]!, 10);
  const northing = parseInt(m[5]!, 10);

  if (zone < 1 || zone > 60) return null;
  if (bandLetter < 'C' || bandLetter > 'X') return null;

  const colSet = zone % 3 === 1 ? 'ABCDEFGH' : zone % 3 === 2 ? 'JKLMNPQR' : 'STUVWXYZ';
  const colLetter = colLetters[0]!;
  const rowLetter = colLetters[1]!;

  const colIdx = colSet.indexOf(colLetter);
  if (colIdx < 0) return null;
  const colSetEastings = colIdx * 100000 + 100000;

  const rowSet = 'ABCDEFGHJKLMNPQRSTUV';
  const rowCycle = rowSet.length;
  let rowIdx: number;
  if (zone % 2 === 0) {
    rowIdx = rowSet.indexOf(rowLetter);
  } else {
    rowIdx = (rowSet.indexOf(rowLetter) + 5) % rowCycle;
  }
  if (rowIdx < 0) return null;

  const bandIdx = bandLetter.charCodeAt(0) - 'C'.charCodeAt(0);
  if (bandIdx >= 10) bandIdx - 1;
  const bandNorthing = bandIdx * 100000;

  const minNorthing = bandNorthing + rowIdx * 100000;
  const numEastingDigits = m[4]!.length;
  const numNorthingDigits = m[5]!.length;
  if (numEastingDigits !== numNorthingDigits) return null;

  const scale = Math.pow(10, 5 - numEastingDigits);
  const fullEasting = colSetEastings + easting * scale;
  const fullNorthing = minNorthing + northing * scale;

  const { lat, lng } = utmToLatLng(zone, fullEasting, fullNorthing, bandLetter);
  return { lat, lng };
}

const RADIUS = 6378137;
const FLATTENING = 1 / 298.257223563;
const K0 = 0.9996;
const E2 = FLATTENING * (2 - FLATTENING);
const E4 = E2 * E2;
const E6 = E4 * E2;
const EP2 = E2 / (1 - E2);

function utmToLatLng(zone: number, easting: number, northing: number, bandLetter: string): { lat: number; lng: number } {
  const x = easting - 500000;
  const y = bandLetter < 'N' ? northing - 10000000 : northing;

  const m = y / K0;
  const mu = m / (RADIUS * (1 - E2 / 4 - 3 * E4 / 64 - 5 * E6 / 256));
  const e1 = (1 - Math.sqrt(1 - E2)) / (1 + Math.sqrt(1 - E2));
  const phi1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu)
    + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu)
    + (151 * e1 ** 3 / 96) * Math.sin(6 * mu);

  const n1 = RADIUS / Math.sqrt(1 - E2 * Math.sin(phi1) ** 2);
  const t1 = Math.tan(phi1) ** 2;
  const c1 = EP2 * Math.cos(phi1) ** 2;
  const r1 = RADIUS * (1 - E2) / Math.pow(1 - E2 * Math.sin(phi1) ** 2, 1.5);
  const d = x / (n1 * K0);

  const lat = phi1 - (n1 * Math.tan(phi1) / r1) * (d ** 2 / 2
    - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * EP2) * d ** 4 / 24
    + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * EP2 - 3 * c1 ** 2) * d ** 6 / 720);

  const lng = (zone - 1) * 6 - 180 + 3 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
    + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * EP2 + 24 * t1 ** 2) * d ** 5 / 120) / Math.cos(phi1);

  return { lat: lat * 180 / Math.PI, lng: lng * 180 / Math.PI };
}
