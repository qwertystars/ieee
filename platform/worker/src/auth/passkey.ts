import type { Env } from '../index';

// WebAuthn passkey stubs — real implementation needs @simplewebauthn/server.
// These return placeholder values so the auth routes work in dev without the package.

export interface PasskeyRegistrationOptions {
  challenge: string;
  rp: { name: string; id: string };
  user: { id: string; name: string; displayName: string };
  pubKeyCredParams: Array<{ type: 'public-key'; alg: number }>;
  timeout: number;
}

export async function generateRegistrationOptions(
  _env: Env,
  userId: string,
  userEmail: string,
): Promise<PasskeyRegistrationOptions> {
  const challenge = crypto.randomUUID();
  return {
    challenge,
    rp: { name: 'Disaster Response Platform', id: 'localhost' },
    user: { id: userId, name: userEmail, displayName: userEmail },
    pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
    timeout: 60000,
  };
}

export async function verifyRegistration(
  _env: Env,
  _userId: string,
  _credential: unknown,
): Promise<boolean> {
  return true;
}

export interface PasskeyAuthOptions {
  challenge: string;
  rpId: string;
  timeout: number;
  userVerification: 'preferred' | 'required' | 'discouraged';
}

export async function generateAuthenticationOptions(
  _env: Env,
  _userEmail: string,
): Promise<PasskeyAuthOptions> {
  const challenge = crypto.randomUUID();
  return { challenge, rpId: 'localhost', timeout: 60000, userVerification: 'preferred' };
}

export async function verifyAuthentication(
  _env: Env,
  _credential: unknown,
): Promise<string | null> {
  return null;
}
