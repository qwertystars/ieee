import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { users, memberships, roles, rolePermissions, incidents } from '../../db/schema';
import { ulid, nowMs } from '../../lib/ulid';
import { sha256 } from '../../lib/audit';

export const seedRoutes = new Hono<AppEnv>();

seedRoutes.post('/demo', async (c) => {
  const db = drizzle(c.env.db);
  const orgId = ulid();
  const adminId = ulid();
  const roleId = ulid();

  await db.insert(roles).values({ id: roleId, orgId, name: 'admin', system: true, createdAt: nowMs() });
  await db.insert(rolePermissions).values({ id: ulid(), roleId, action: '*', subject: '*' });
  await db.insert(users).values({
    id: adminId, orgId, email: 'admin@demo.disaster', name: 'Demo Admin',
    role: 'admin', status: 'active', passwordHash: await sha256('demo1234'),
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  await db.insert(memberships).values({ id: ulid(), userId: adminId, orgId, roleId, createdAt: nowMs() });

  const incidentId = ulid();
  await db.insert(incidents).values({
    id: incidentId, orgId, type: 'flood', severity: 'severe', status: 'active',
    title: 'Rivertown Flood', description: 'Major river overflow affecting downtown',
    geometry: JSON.stringify({ type: 'Polygon', coordinates: [[[-122.4, 37.8], [-122.4, 37.9], [-122.3, 37.9], [-122.3, 37.8], [-122.4, 37.8]]] }),
    startsAt: nowMs(), createdAt: nowMs(), updatedAt: nowMs(),
  });

  return c.json({ orgId, adminId, incidentId, login: { email: 'admin@demo.disaster', password: 'demo1234' } }, 201);
});
