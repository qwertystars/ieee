import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { incidents, memberships } from '../../db/schema';
import { eq } from 'drizzle-orm';

export const dashboardRoutes = new Hono<AppEnv>();

const ROLE_DASHBOARDS = [
  'admin', 'operator', 'field_responder', 'public_information',
  'volunteer', 'shelter_manager', 'medical', 'logistics',
  'command_center', 'liaison', 'donor',
] as const;

dashboardRoutes.get('/:role', async (c) => {
  const role = c.req.param('role');
  if (!ROLE_DASHBOARDS.includes(role as typeof ROLE_DASHBOARDS[number])) {
    return c.json({ error: { code: 'INVALID_ROLE', message: `Unknown role: ${role}`, request_id: c.get('requestId') } }, 400);
  }

  const db = drizzle(c.env.db);
  const orgId = c.get('orgId');
  if (!orgId) return c.json({ error: { code: 'NO_ORG', message: 'Organization context required', request_id: c.get('requestId') } }, 400);

  const activeIncidents = await db.select({ id: incidents.id, title: incidents.title, status: incidents.status, severity: incidents.severity })
    .from(incidents).where(eq(incidents.orgId, orgId)).limit(10).all();

  return c.json({ role, orgId, activeIncidents, summary: { totalIncidents: activeIncidents.length } });
});

dashboardRoutes.post('/org-switch', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const orgId = body.orgId;
  if (!orgId) return c.json({ error: { code: 'MISSING_ORG', message: 'orgId required', request_id: c.get('requestId') } }, 400);

  const db = drizzle(c.env.db);
  const userId = c.get('orgId') as string;
  const m = await db.select().from(memberships).where(eq(memberships.userId, userId)).limit(20).all();
  const hasMembership = m.some((mem) => mem.orgId === orgId);
  if (!hasMembership) return c.json({ error: { code: 'NOT_MEMBER', message: 'Not a member of this org', request_id: c.get('requestId') } }, 403);

  return c.json({ ok: true, activeOrgId: orgId });
});

dashboardRoutes.get('/memberships', async (c) => {
  const userId = c.get('orgId') as string;
  const db = drizzle(c.env.db);
  const result = await db.select().from(memberships).where(eq(memberships.userId, userId)).limit(50).all();
  return c.json({ items: result });
});

dashboardRoutes.post('/invite', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const token = crypto.randomUUID();
  return c.json({ inviteToken: token, role: body.role ?? 'viewer', orgId: body.orgId });
});
