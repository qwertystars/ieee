import type { Env } from '../index';

// WebAuthn passkey implementation using PasskeyDO for challenge/credential storage.
// The DO handles challenge lifecycle and credential registry; this module generates
// options and delegates verification.

export interface PasskeyRegistrationOptions {
  challenge: string;
  rp: { name: string; id: string };
  user: { id: string; name: string; displayName: string };
  pubKeyCredParams: Array<{ type: 'public-key'; alg: number }>;
  timeout: number;
}

export async function generateRegistrationOptions(
  env: Env,
  userId: string,
  userEmail: string,
): Promise<PasskeyRegistrationOptions> {
  const challenge = crypto.randomUUID();
  const doId = env.PasskeyDO.idFromName(userEmail);
  const doStub = env.PasskeyDO.get(doId);
  await doStub.fetch(new Request('https://do.local/challenge/store', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ challenge, userId, userEmail, type: 'registration' }),
  }));
  return {
    challenge,
    rp: { name: 'Disaster Response Platform', id: 'localhost' },
    user: { id: userId, name: userEmail, displayName: userEmail },
    pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
    timeout: 60000,
  };
}

export async function verifyRegistration(
  env: Env,
  userEmail: string,
  credential: unknown,
): Promise<boolean> {
  const cred = credential as { id?: string; publicKey?: string; type?: string; response?: { clientDataJSON?: string } };
  if (!cred?.id || !cred?.publicKey) return false;

  const doId = env.PasskeyDO.idFromName(userEmail);
  const doStub = env.PasskeyDO.get(doId);
  const resp = await doStub.fetch(new Request('https://do.local/credential/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      credentialId: cred.id,
      publicKey: cred.publicKey,
      deviceType: cred.type ?? 'unknown',
    }),
  }));
  return resp.ok;
}

export interface PasskeyAuthOptions {
  challenge: string;
  rpId: string;
  timeout: number;
  userVerification: 'preferred' | 'required' | 'discouraged';
}

export async function generateAuthenticationOptions(
  env: Env,
  userEmail: string,
): Promise<PasskeyAuthOptions> {
  const challenge = crypto.randomUUID();
  const doId = env.PasskeyDO.idFromName(userEmail);
  const doStub = env.PasskeyDO.get(doId);
  await doStub.fetch(new Request('https://do.local/challenge/store', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ challenge, userId: userEmail, userEmail, type: 'authentication' }),
  }));
  return { challenge, rpId: 'localhost', timeout: 60000, userVerification: 'preferred' };
}

export async function verifyAuthentication(
  env: Env,
  credential: unknown,
): Promise<string | null> {
  const cred = credential as { id?: string; response?: { clientDataJSON?: string } };
  if (!cred?.id) return null;

  const doId = env.PasskeyDO.idFromName(cred.id);
  const doStub = env.PasskeyDO.get(doId);
  const resp = await doStub.fetch(new Request('https://do.local/credential/lookup?' + new URLSearchParams({ credentialId: cred.id })));
  if (!resp.ok) return null;
  const result = await resp.json() as { ok: boolean; credential?: { credentialId: string } };
  if (!result.ok || !result.credential) return null;
  return result.credential.credentialId;
}
