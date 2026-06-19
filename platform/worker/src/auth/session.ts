import type { Env } from '../index';
import { drizzle } from 'drizzle-orm/d1';
import { sessions, devices } from '../db/schema';
import { eq } from 'drizzle-orm';
import { ulid, nowMs } from '../lib/ulid';
import { sha256 } from '../lib/audit';

const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export async function createSession(
  env: Env,
  userId: string,
  _orgId: string,
  deviceId: string | null,
): Promise<{ token: string; expiresAt: number }> {
  const db = drizzle(env.db);
  const token = crypto.randomUUID();
  const tokenHash = await sha256(token);
  const expiresAt = nowMs() + SESSION_TTL_MS;
  const id = ulid();

  await db.insert(sessions).values({
    id,
    userId,
    deviceId,
    tokenHash,
    expiresAt,
    createdAt: nowMs(),
  });

  return { token, expiresAt };
}

export async function validateSession(
  env: Env,
  token: string,
): Promise<{ userId: string; sessionId: string } | null> {
  const db = drizzle(env.db);
  const tokenHash = await sha256(token);
  const now = nowMs();

  const result = await db
    .select()
    .from(sessions)
    .where(eq(sessions.tokenHash, tokenHash))
    .limit(1)
    .all();

  const session = result[0];
  if (!session) return null;
  if (session.expiresAt < now) return null;

  return { userId: session.userId, sessionId: session.id };
}

export async function revokeSession(env: Env, sessionId: string): Promise<void> {
  const db = drizzle(env.db);
  await db.update(sessions).set({ expiresAt: 0 }).where(eq(sessions.id, sessionId));
}

export async function recordDevice(
  env: Env,
  userId: string,
  userAgent: string | null,
  ip: string | null,
  fingerprint: string | null,
): Promise<string> {
  const db = drizzle(env.db);
  const id = ulid();
  await db.insert(devices).values({
    id,
    userId,
    userAgent,
    lastIp: ip,
    fingerprint,
    lastSeenAt: nowMs(),
    createdAt: nowMs(),
  });
  return id;
}
