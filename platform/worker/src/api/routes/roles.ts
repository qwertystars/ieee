import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { roles, rolePermissions } from '../../db/schema';
import { eq } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const rolesRoutes = new Hono<AppEnv>();

rolesRoutes.get('/:orgId/roles', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(roles).where(eq(roles.orgId, c.req.param('orgId'))).all();
  return c.json({ items: result });
});

rolesRoutes.post('/:orgId/roles', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.req.param('orgId');
  const id = ulid();

  const db = drizzle(c.env.db);
  await db.insert(roles).values({
    id,
    orgId,
    name: body.name as string,
    system: false,
    createdAt: nowMs(),
  });

  if (Array.isArray(body.permissions)) {
    for (const perm of body.permissions as Array<{ action: string; subject: string }>) {
      await db.insert(rolePermissions).values({
        id: ulid(),
        roleId: id,
        action: perm.action,
        subject: perm.subject,
      });
    }
  }

  await writeAudit({ db, orgId, actor: c.get('orgId') ?? 'system', action: 'role.create', entity: `role:${id}`, after: body });
  return c.json({ id, name: body.name }, 201);
});

rolesRoutes.patch('/:orgId/roles/:roleId', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const db = drizzle(c.env.db);
  await db.update(roles).set({ name: body.name as string }).where(eq(roles.id, c.req.param('roleId')));
  return c.json({ ok: true });
});

rolesRoutes.delete('/:orgId/roles/:roleId', async (c) => {
  const roleId = c.req.param('roleId');
  const db = drizzle(c.env.db);

  const existing = await db.select().from(roles).where(eq(roles.id, roleId)).limit(1).all();
  if (existing[0]?.system) {
    return c.json({ error: { code: 'SYSTEM_ROLE', message: 'Cannot delete system role', request_id: c.get('requestId') } }, 400);
  }

  await db.delete(roles).where(eq(roles.id, roleId));
  return c.json({ ok: true });
});

rolesRoutes.get('/:orgId/roles/:roleId/permissions', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(rolePermissions).where(eq(rolePermissions.roleId, c.req.param('roleId'))).all();
  return c.json({ items: result });
});

rolesRoutes.post('/:orgId/roles/:roleId/permissions', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const db = drizzle(c.env.db);
  const id = ulid();
  await db.insert(rolePermissions).values({
    id,
    roleId: c.req.param('roleId'),
    action: body.action,
    subject: body.subject,
  });
  return c.json({ id }, 201);
});

rolesRoutes.delete('/:orgId/roles/:roleId/permissions/:permId', async (c) => {
  const db = drizzle(c.env.db);
  await db.delete(rolePermissions).where(eq(rolePermissions.id, c.req.param('permId')));
  return c.json({ ok: true });
});
