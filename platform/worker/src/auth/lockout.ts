import type { Env } from '../index';
import { drizzle } from 'drizzle-orm/d1';
import { orgs } from '../db/schema';
import { eq } from 'drizzle-orm';
import { writeAudit } from '../lib/audit';
import { nowMs } from '../lib/ulid';

export async function enableLockout(env: Env, orgId: string, actorUserId: string): Promise<void> {
  const db = drizzle(env.db);
  await db.update(orgs).set({ locked: true, updatedAt: nowMs() }).where(eq(orgs.id, orgId));
  await writeAudit({ db, orgId, actor: actorUserId, action: 'lockout.enable', entity: `org:${orgId}`, before: { locked: false }, after: { locked: true } });
}

export async function disableLockout(env: Env, orgId: string, actorUserId: string): Promise<void> {
  const db = drizzle(env.db);
  await db.update(orgs).set({ locked: false, updatedAt: nowMs() }).where(eq(orgs.id, orgId));
  await writeAudit({ db, orgId, actor: actorUserId, action: 'lockout.disable', entity: `org:${orgId}`, before: { locked: true }, after: { locked: false } });
}

export async function isLocked(env: Env, orgId: string): Promise<boolean> {
  const db = drizzle(env.db);
  const result = await db.select({ locked: orgs.locked }).from(orgs).where(eq(orgs.id, orgId)).limit(1).all();
  return result[0]?.locked ?? false;
}
