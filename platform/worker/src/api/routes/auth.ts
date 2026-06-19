function parseCookie(header: string, name: string): string | undefined { const m = header.match(new RegExp(name + "=([^;]+)")); return m?.[1]; }
import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { users } from '../../db/schema';
import { eq } from 'drizzle-orm';
import { sha256 } from '../../lib/audit';
import { createSession, validateSession, revokeSession, recordDevice } from '../../auth/session';
import { enableLockout, disableLockout, isLocked } from '../../auth/lockout';
import { checkAnomalousLogin } from '../../auth/anomaly';
import {
  generateRegistrationOptions,
  verifyRegistration,
  generateAuthenticationOptions,
  verifyAuthentication,
} from '../../auth/passkey';
import { writeAudit } from '../../lib/audit';

export const authRoutes = new Hono<AppEnv>();

authRoutes.post('/login', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const email = body.email;
  const password = body.password;
  if (!email || !password) {
    return c.json({ error: { code: 'MISSING_CREDENTIALS', message: 'Email and password required', request_id: c.get('requestId') } }, 400);
  }

  const db = drizzle(c.env.db);
  const userResult = await db.select().from(users).where(eq(users.email, email)).limit(1).all();
  const user = userResult[0];
  if (!user) {
    return c.json({ error: { code: 'INVALID_CREDENTIALS', message: 'Invalid email or password', request_id: c.get('requestId') } }, 401);
  }

  const passwordHash = await sha256(password);
  if (user.passwordHash !== passwordHash) {
    await writeAudit({ db, orgId: user.orgId, actor: user.id, action: 'login.failed', entity: `user:${user.id}`, after: { reason: 'wrong_password' } });
    return c.json({ error: { code: 'INVALID_CREDENTIALS', message: 'Invalid email or password', request_id: c.get('requestId') } }, 401);
  }

  const locked = await isLocked(c.env, user.orgId);
  if (locked) {
    return c.json({ error: { code: 'ORG_LOCKED', message: 'Organization is in emergency lockout', request_id: c.get('requestId') } }, 423);
  }

  const fingerprint = c.req.header('X-Device-Fingerprint') ?? crypto.randomUUID();
  const ip = c.req.header('CF-Connecting-IP') ?? '0.0.0.0';
  const deviceId = await recordDevice(c.env, user.id, c.req.header('User-Agent') ?? null, ip, fingerprint);

  const { token, expiresAt } = await createSession(c.env, user.id, user.orgId, deviceId);

  const anomalous = await checkAnomalousLogin(c.env, user.id, fingerprint, ip);
  await writeAudit({ db, orgId: user.orgId, actor: user.id, action: 'login.success', entity: `user:${user.id}`, after: { anomalous: anomalous.anomalous, reason: anomalous.reason } });

  c.header('Set-Cookie', `session=${token}; HttpOnly; Secure; SameSite=Strict; Max-Age=${Math.floor((expiresAt - Date.now()) / 1000)}`);
  return c.json({ token, user: { id: user.id, email: user.email, name: user.name, role: user.role }, anomalous: anomalous.anomalous });
});

authRoutes.post('/passkey/register-begin', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  if (!body.email) return c.json({ error: { code: 'MISSING_EMAIL', message: 'Email required', request_id: c.get('requestId') } }, 400);
  const options = await generateRegistrationOptions(c.env, crypto.randomUUID(), body.email);
  return c.json(options);
});

authRoutes.post('/passkey/register-finish', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const ok = await verifyRegistration(c.env, '', body.credential);
  return c.json({ verified: ok });
});

authRoutes.post('/passkey/login-begin', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  if (!body.email) return c.json({ error: { code: 'MISSING_EMAIL', message: 'Email required', request_id: c.get('requestId') } }, 400);
  const options = await generateAuthenticationOptions(c.env, body.email);
  return c.json(options);
});

authRoutes.post('/passkey/login-finish', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const userId = await verifyAuthentication(c.env, body.credential);
  if (!userId) return c.json({ error: { code: 'PASSKEY_FAILED', message: 'Passkey verification failed', request_id: c.get('requestId') } }, 401);
  return c.json({ userId });
});

authRoutes.post('/logout', async (c) => {
  const token = c.req.header('Authorization')?.replace('Bearer ', '') ?? '';
  const session = await validateSession(c.env, token);
  if (session) await revokeSession(c.env, session.sessionId);
  c.header('Set-Cookie', 'session=; HttpOnly; Secure; Max-Age=0');
  return c.json({ ok: true });
});

authRoutes.get('/me', async (c) => {
  const token = c.req.header('Authorization')?.replace('Bearer ', '') ?? parseCookie(c.req.header('Cookie') ?? '', 'session') ?? '';
  const session = await validateSession(c.env, token);
  if (!session) return c.json({ error: { code: 'UNAUTHENTICATED', message: 'No valid session', request_id: c.get('requestId') } }, 401);

  const db = drizzle(c.env.db);
  const userResult = await db.select().from(users).where(eq(users.id, session.userId)).limit(1).all();
  const user = userResult[0];
  if (!user) return c.json({ error: { code: 'USER_NOT_FOUND', message: 'User not found', request_id: c.get('requestId') } }, 404);

  return c.json({ id: user.id, email: user.email, name: user.name, role: user.role, orgId: user.orgId, status: user.status });
});

authRoutes.post('/lockout', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, string>));
  const orgId = body.orgId;
  const actorUserId = body.actorUserId;
  if (!orgId || !actorUserId) return c.json({ error: { code: 'MISSING_PARAMS', message: 'orgId and actorUserId required', request_id: c.get('requestId') } }, 400);

  const enable = body.enable !== false;
  if (enable) await enableLockout(c.env, orgId, actorUserId);
  else await disableLockout(c.env, orgId, actorUserId);

  return c.json({ ok: true, locked: enable });
});
