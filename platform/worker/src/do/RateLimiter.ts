import type { Env } from '../index';

export class RateLimiter implements DurableObject {
  state: DurableObjectState;
  env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get('key') ?? 'default';
    const limit = parseInt(url.searchParams.get('limit') ?? '100');
    const window = parseInt(url.searchParams.get('window') ?? '60');

    const now = Math.floor(Date.now() / 1000);
    const bucket = (await this.state.storage.get<{ count: number; resetAt: number }>(`bucket:${key}`)) ?? { count: 0, resetAt: now + window };

    if (now >= bucket.resetAt) {
      bucket.count = 0;
      bucket.resetAt = now + window;
    }

    if (bucket.count >= limit) {
      return new Response(JSON.stringify({ allowed: false, retryAfter: bucket.resetAt - now }), {
        status: 429,
        headers: { 'Content-Type': 'application/json', 'Retry-After': String(bucket.resetAt - now) },
      });
    }

    bucket.count++;
    await this.state.storage.put(`bucket:${key}`, bucket);
    return new Response(JSON.stringify({ allowed: true, remaining: limit - bucket.count, resetAt: bucket.resetAt }), {
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
