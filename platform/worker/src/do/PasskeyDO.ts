import type { Env } from '../index';

// PasskeyDO — WebAuthn challenge storage and credential registry.
// One per user; stores challenges (with expiry) and registered credentials.
// Storage: challenges:{challengeId}, credentials:{credentialId}

interface StoredChallenge {
  challenge: string;
  userId: string;
  userEmail: string;
  type: 'registration' | 'authentication';
  createdAt: number;
  expiresAt: number;
}

interface StoredCredential {
  credentialId: string;
  publicKey: string;
  counter: number;
  deviceType: string;
  createdAt: number;
}

const CHALLENGE_TTL_MS = 5 * 60 * 1000; // 5 minutes

export class PasskeyDO implements DurableObject {
  constructor(readonly state: DurableObjectState, readonly env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/challenge/store' && request.method === 'POST') {
      const body = await request.json() as {
        challenge: string;
        userId: string;
        userEmail: string;
        type: 'registration' | 'authentication';
      };
      const challengeId = crypto.randomUUID();
      const stored: StoredChallenge = {
        challenge: body.challenge,
        userId: body.userId,
        userEmail: body.userEmail,
        type: body.type,
        createdAt: Date.now(),
        expiresAt: Date.now() + CHALLENGE_TTL_MS,
      };
      await this.state.storage.put(`challenges:${challengeId}`, stored);
      return Response.json({ ok: true, challengeId });
    }

    if (url.pathname === '/challenge/verify' && request.method === 'POST') {
      const body = await request.json() as { challengeId: string; challenge: string };
      const stored = await this.state.storage.get<StoredChallenge>(`challenges:${body.challengeId}`);
      if (!stored) {
        return Response.json({ ok: false, error: 'CHALLENGE_NOT_FOUND' }, { status: 404 });
      }
      if (Date.now() > stored.expiresAt) {
        await this.state.storage.delete(`challenges:${body.challengeId}`);
        return Response.json({ ok: false, error: 'CHALLENGE_EXPIRED' }, { status: 410 });
      }
      if (stored.challenge !== body.challenge) {
        return Response.json({ ok: false, error: 'CHALLENGE_MISMATCH' }, { status: 400 });
      }
      // Consume the challenge (one-time use)
      await this.state.storage.delete(`challenges:${body.challengeId}`);
      return Response.json({
        ok: true,
        userId: stored.userId,
        userEmail: stored.userEmail,
        type: stored.type,
      });
    }

    if (url.pathname === '/credential/register' && request.method === 'POST') {
      const body = await request.json() as {
        credentialId: string;
        publicKey: string;
        deviceType: string;
      };
      const existing = await this.state.storage.get<StoredCredential>(`credentials:${body.credentialId}`);
      if (existing) {
        return Response.json({ ok: false, error: 'CREDENTIAL_EXISTS' }, { status: 409 });
      }
      const cred: StoredCredential = {
        credentialId: body.credentialId,
        publicKey: body.publicKey,
        counter: 0,
        deviceType: body.deviceType,
        createdAt: Date.now(),
      };
      await this.state.storage.put(`credentials:${body.credentialId}`, cred);
      return Response.json({ ok: true, credentialId: body.credentialId }, { status: 201 });
    }

    if (url.pathname === '/credential/lookup' && request.method === 'GET') {
      const credentialId = url.searchParams.get('credentialId');
      if (!credentialId) {
        return Response.json({ ok: false, error: 'MISSING_CREDENTIAL_ID' }, { status: 400 });
      }
      const cred = await this.state.storage.get<StoredCredential>(`credentials:${credentialId}`);
      if (!cred) {
        return Response.json({ ok: false, error: 'CREDENTIAL_NOT_FOUND' }, { status: 404 });
      }
      return Response.json({ ok: true, credential: cred });
    }

    if (url.pathname === '/credential/update-counter' && request.method === 'POST') {
      const body = await request.json() as { credentialId: string; counter: number };
      const cred = await this.state.storage.get<StoredCredential>(`credentials:${body.credentialId}`);
      if (!cred) {
        return Response.json({ ok: false, error: 'CREDENTIAL_NOT_FOUND' }, { status: 404 });
      }
      if (body.counter <= cred.counter) {
        return Response.json({ ok: false, error: 'COUNTER_ROLLBACK' }, { status: 409 });
      }
      cred.counter = body.counter;
      await this.state.storage.put(`credentials:${body.credentialId}`, cred);
      return Response.json({ ok: true });
    }

    if (url.pathname === '/credentials/list' && request.method === 'GET') {
      const list = await this.state.storage.list<StoredCredential>({ prefix: 'credentials:' });
      const credentials = Array.from(list.values());
      return Response.json({ ok: true, credentials, count: credentials.length });
    }

    return new Response('Not found', { status: 404 });
  }
}
