import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('API client', () => {
  const originalFetch = globalThis.fetch;
  const originalLocalStorage = globalThis.localStorage;

  beforeEach(() => {
    const store = new Map<string, string>();
    const ls = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, v); },
      removeItem: (k: string) => { store.delete(k); },
      clear: () => { store.clear(); },
      key: (i: number) => Array.from(store.keys())[i] ?? null,
      get length() { return store.size; },
    };
    Object.defineProperty(globalThis, 'localStorage', { value: ls, writable: true, configurable: true });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'localStorage', { value: originalLocalStorage, writable: true, configurable: true });
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('getToken returns null when no token stored', async () => {
    const { api } = await import('../src/lib/api');
    expect(api.getToken()).toBeNull();
  });

  it('setToken / getToken round-trips a token', async () => {
    const { api } = await import('../src/lib/api');
    api.setToken('test-token-123');
    expect(api.getToken()).toBe('test-token-123');
    api.setToken(null);
    expect(api.getToken()).toBeNull();
  });

  it('login stores token and returns user', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ token: 'abc', user: { id: 'u1', email: 'a@b.c', name: 'A', role: 'admin' } }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { api } = await import('../src/lib/api');
    const result = await api.login('a@b.c', 'pw');
    expect(result.token).toBe('abc');
    expect(result.user.role).toBe('admin');
    expect(api.getToken()).toBe('abc');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toMatch(/\/api\/auth\/login$/);
    expect((init as RequestInit).method).toBe('POST');
    const authHeader = ((init as RequestInit).headers as Record<string, string>).Authorization;
    expect(authHeader).toBeUndefined();
  });

  it('me sends Authorization header when token is set', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'u1', email: 'a@b.c', name: 'A', role: 'admin', orgId: 'o1', status: 'active' }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { api } = await import('../src/lib/api');
    api.setToken('bearer-xyz');
    await api.me();
    const [, init] = fetchMock.mock.calls[0]!;
    expect(((init as RequestInit).headers as Record<string, string>).Authorization).toBe('Bearer bearer-xyz');
  });

  it('logout clears token even when request fails', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('network'));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { api } = await import('../src/lib/api');
    api.setToken('will-be-cleared');
    await api.logout();
    expect(api.getToken()).toBeNull();
  });

  it('request throws on non-OK response with error message', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { message: 'Invalid credentials' } }), {
        status: 401, headers: { 'Content-Type': 'application/json' },
      }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { api } = await import('../src/lib/api');
    await expect(api.login('bad@b.c', 'wrong')).rejects.toThrow('Invalid credentials');
  });
});
