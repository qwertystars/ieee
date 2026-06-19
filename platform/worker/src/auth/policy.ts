import { drizzle } from 'drizzle-orm/d1';
import { rolePermissions, memberships } from '../db/schema';
import { eq, and } from 'drizzle-orm';

export async function can(
  db: ReturnType<typeof drizzle>,
  orgId: string,
  userId: string,
  action: string,
  subject: string,
): Promise<boolean> {
  const perms = await getPermissions(db, orgId, userId);
  return perms.some((p) => {
    const actionMatch = p.action === '*' || p.action === action;
    const subjectMatch = p.subject === '*' || p.subject === subject;
    return actionMatch && subjectMatch;
  });
}

export async function getPermissions(
  db: ReturnType<typeof drizzle>,
  orgId: string,
  userId: string,
): Promise<Array<{ action: string; subject: string }>> {
  const result = await db
    .select({ action: rolePermissions.action, subject: rolePermissions.subject })
    .from(rolePermissions)
    .innerJoin(memberships, eq(memberships.roleId, rolePermissions.roleId))
    .where(and(eq(memberships.userId, userId), eq(memberships.orgId, orgId)))
    .all();

  return result;
}
