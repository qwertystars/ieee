import type { Env } from '../index';

const DEV_ENVS = new Set(['development', 'local', 'test']);

export async function presignUpload(
  env: Env,
  bucket: 'media' | 'exports',
  key: string,
  contentType: string,
  expirySeconds = 3600,
): Promise<string> {
  const encodedKey = encodeURIComponent(key);

  if (DEV_ENVS.has(env.ENVIRONMENT)) {
    return `https://r2.local/${bucket}/${encodedKey}?upload=true&contentType=${encodeURIComponent(contentType)}`;
  }

  const expires = Date.now() + expirySeconds * 1000;
  const sig = await signR2Url(bucket, key, expires, 'upload');
  return `https://r2.local/${bucket}/${encodedKey}?expires=${expires}&sig=${sig}`;
}

export async function presignDownload(
  env: Env,
  bucket: 'media' | 'exports',
  key: string,
  expirySeconds = 3600,
): Promise<string> {
  const encodedKey = encodeURIComponent(key);

  if (DEV_ENVS.has(env.ENVIRONMENT)) {
    return `https://r2.local/${bucket}/${encodedKey}`;
  }

  const expires = Date.now() + expirySeconds * 1000;
  const sig = await signR2Url(bucket, key, expires, 'download');
  return `https://r2.local/${bucket}/${encodedKey}?expires=${expires}&sig=${sig}`;
}

async function signR2Url(bucket: string, key: string, expires: number, method: string): Promise<string> {
  const data = `${method}:${bucket}:${key}:${expires}`;
  const encoder = new TextEncoder();
  const buffer = encoder.encode(data);
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
