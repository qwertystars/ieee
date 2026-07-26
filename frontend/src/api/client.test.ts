// Unit tests for the typed API client.
// Mocks global fetch; exercises real request() logic (URL building, auth header
// injection, error extraction, 204 handling, offline outbox routing).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, request } from './client'
import { clearToken, getToken, setToken } from './token'

// --- fetch mock helper ---------------------------------------------------

type FetchMock = typeof fetch & { mockClear: () => void }

function mockFetch(responses: Array<{
  url?: RegExp
  method?: string
  status?: number
  body?: unknown
  text?: string
  headers?: Record<string, string>
}>): FetchMock {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    calls.push({ url, init: init ?? {} })
    const match = responses.find(r => {
      if (r.url && !r.url.test(url)) return false
      if (r.method && init?.method && r.method !== init.method) return false
      return true
    })
    if (!match) throw new Error(`unexpected fetch: ${init?.method ?? 'GET'} ${url}`)
    const status = match.status ?? 200
    // 204 must not carry a body per the Response constructor contract.
    const text = status === 204
      ? null
      : (match.text ?? (match.body === undefined ? '' : JSON.stringify(match.body)))
    return new Response(text, {
      status,
      headers: match.headers,
    })
  }) as unknown as FetchMock
  fn.mockClear = () => { calls.length = 0; vi.mocked(fn).mockClear() }
  // expose calls for assertions
  ;(fn as unknown as { _calls: typeof calls })._calls = calls
  return fn
}

function lastCall(mock: FetchMock) {
  const calls = (mock as unknown as { _calls: Array<{ url: string; init: RequestInit }> })._calls
  return calls[calls.length - 1]
}

// --- tests ----------------------------------------------------------------

beforeEach(() => {
  clearToken()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('api.login', () => {
  it('POSTs form-encoded credentials to /api/auth/login and stores the access token', async () => {
    const fetchMock = mockFetch([
      {
        url: /\/api\/auth\/login$/,
        method: 'POST',
        status: 200,
        body: { access_token: 'jwt-abc', token_type: 'bearer' },
      },
    ])
    vi.stubGlobal('fetch', fetchMock)

    const res = await api.login('admin@demo.disaster', 'demo1234')

    expect(res.access_token).toBe('jwt-abc')
    expect(getToken()).toBe('jwt-abc')

    const call = lastCall(fetchMock)!
    expect(call.init.method).toBe('POST')
    // Body must be URLSearchParams, not JSON.
    const body = call.init.body as URLSearchParams
    expect(body).toBeInstanceOf(URLSearchParams)
    expect(body.get('username')).toBe('admin@demo.disaster')
    expect(body.get('password')).toBe('demo1234')
    // Form requests set the urlencoded content type.
    expect((call.init.headers as Record<string, string>)['Content-Type'])
      .toBe('application/x-www-form-urlencoded')
  })

  it('throws ApiError on 401 and does NOT store a token', async () => {
    const fetchMock = mockFetch([
      {
        url: /\/api\/auth\/login$/,
        method: 'POST',
        status: 401,
        body: { detail: 'Invalid credentials' },
      },
    ])
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.login('x@y.z', 'wrong')).rejects.toMatchObject({
      name: 'ApiError',
      status: 401,
      detail: 'Invalid credentials',
    })
    expect(getToken()).toBeNull()
  })
})

describe('api.getMe', () => {
  it('sends Bearer token header when a token is stored', async () => {
    setToken('jwt-xyz')
    const fetchMock = mockFetch([
      {
        url: /\/api\/auth\/me$/,
        method: 'GET',
        status: 200,
        body: { id: 'u1', email: 'a@b.c', role: 'admin', org_id: 'org-1' },
      },
    ])
    vi.stubGlobal('fetch', fetchMock)

    const user = await api.getMe()
    expect(user.email).toBe('a@b.c')
    const headers = lastCall(fetchMock)!.init.headers as Record<string, string>
    expect(headers['Authorization']).toBe('Bearer jwt-xyz')
  })

  it('omits Authorization header when no token is stored', async () => {
    const fetchMock = mockFetch([
      {
        url: /\/api\/auth\/me$/,
        method: 'GET',
        status: 200,
        body: { id: 'u1', email: 'a@b.c', role: 'admin', org_id: 'org-1' },
      },
    ])
    vi.stubGlobal('fetch', fetchMock)

    await api.getMe()
    const headers = lastCall(fetchMock)!.init.headers as Record<string, string>
    expect(headers['Authorization']).toBeUndefined()
  })
})

describe('api.logout', () => {
  it('POSTs /api/auth/logout and clears the token on success', async () => {
    setToken('jwt-out')
    const fetchMock = mockFetch([
      { url: /\/api\/auth\/logout$/, method: 'POST', status: 204, text: '' },
    ])
    vi.stubGlobal('fetch', fetchMock)

    await api.logout()
    expect(getToken()).toBeNull()
  })

  it('clears the token even when the server returns an error', async () => {
    setToken('jwt-out')
    const fetchMock = mockFetch([
      { url: /\/api\/auth\/logout$/, method: 'POST', status: 500, body: { detail: 'boom' } },
    ])
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.logout()).rejects.toBeInstanceOf(ApiError)
    // Critical: token must be cleared regardless of server response.
    expect(getToken()).toBeNull()
  })
})

describe('api.getIncidents', () => {
  it('GETs /api/incidents and returns the parsed body', async () => {
    const fetchMock = mockFetch([
      {
        url: /\/api\/incidents(\?|$)/,
        method: 'GET',
        status: 200,
        body: { incidents: [{ id: 'inc-1', title: 'Flood' }], count: 1 },
      },
    ])
    vi.stubGlobal('fetch', fetchMock)

    const res = await api.getIncidents()
    expect(res.count).toBe(1)
    expect(res.incidents[0].id).toBe('inc-1')
  })
})

describe('api.getObservations', () => {
  it('appends incident_id as a query parameter', async () => {
    const fetchMock = mockFetch([
      {
        url: /\/api\/observations\?incident_id=inc-1/,
        method: 'GET',
        status: 200,
        body: { type: 'FeatureCollection', features: [] },
      },
    ])
    vi.stubGlobal('fetch', fetchMock)

    await api.getObservations('inc-1')
    const url = lastCall(fetchMock)!.url
    expect(url).toContain('incident_id=inc-1')
  })
})

describe('api.updateTaskStatus', () => {
  it('PATCHes /api/tasks/:id with a JSON body', async () => {
    const fetchMock = mockFetch([
      {
        url: /\/api\/tasks\/task-9$/,
        method: 'PATCH',
        status: 200,
        body: { id: 'task-9', status: 'completed' },
      },
    ])
    vi.stubGlobal('fetch', fetchMock)

    const task = await api.updateTaskStatus('task-9', { status: 'completed' })
    expect(task.status).toBe('completed')
    const call = lastCall(fetchMock)!
    expect(call.init.method).toBe('PATCH')
    expect((call.init.headers as Record<string, string>)['Content-Type'])
      .toBe('application/json')
    expect(call.init.body).toBe(JSON.stringify({ status: 'completed' }))
  })
})

describe('request — error handling', () => {
  it('wraps network errors in ApiError with status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed to fetch')))

    await expect(request('/api/incidents')).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
      detail: 'failed to fetch',
    })
  })

  it('extracts detail string from error body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Validation failed' }), { status: 422 }),
    ))
    await expect(request('/api/x')).rejects.toMatchObject({
      status: 422,
      detail: 'Validation failed',
    })
  })

  it('joins detail array elements into a single string (FastAPI validation shape)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: ['field required', 'must be positive'] }),
        { status: 422 },
      ),
    ))
    try {
      await request('/api/x')
      expect.fail('should have thrown')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      // extractDetail joins array elements with '; '.
      expect((e as ApiError).detail).toBe('field required; must be positive')
    }
  })

  it('returns undefined for 204 No Content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(request('/api/x', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('falls back to statusText when body has no detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('', { status: 503, statusText: 'Service Unavailable' }),
    ))
    await expect(request('/api/x')).rejects.toMatchObject({
      status: 503,
      detail: 'Service Unavailable',
    })
  })
})

describe('request — offline outbox routing', () => {
  it('routes mutations to the outbox when navigator.onLine is false', async () => {
    // Force offline.
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    })

    const fetchMock = mockFetch([])
    vi.stubGlobal('fetch', fetchMock)

    // A POST to a non-auth endpoint should be queued, not fetched.
    const result = await request('/api/incidents/inc-1/tasks', {
      method: 'POST',
      body: { title: 'Rescue' },
    })

    expect(result).toBeUndefined()
    expect(fetchMock).not.toHaveBeenCalled()

    // Restore online state.
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: true,
    })
  })

  it('throws ApiError for auth endpoints while offline (never queued)', async () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    })
    vi.stubGlobal('fetch', vi.fn())

    await expect(
      request('/api/auth/login', { method: 'POST', form: new URLSearchParams() }),
    ).rejects.toMatchObject({
      status: 0,
    })

    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: true,
    })
  })

  it('still performs GETs while offline (reads are not queued)', async () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    })
    const fetchMock = mockFetch([
      { url: /\/api\/incidents$/, method: 'GET', status: 200, body: { incidents: [], count: 0 } },
    ])
    vi.stubGlobal('fetch', fetchMock)

    const res = await request('/api/incidents')
    expect(res).toEqual({ incidents: [], count: 0 })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: true,
    })
  })
})

describe('request — query parameter building', () => {
  it('omits undefined, null, and empty-string query values', async () => {
    const fetchMock = mockFetch([
      { url: /\/api\/x\?keep=1/, method: 'GET', status: 200, body: { ok: true } },
    ])
    vi.stubGlobal('fetch', fetchMock)

    await request('/api/x', {
      query: { keep: 1, dropUndef: undefined, dropNull: null, dropEmpty: '' },
    })
    const url = lastCall(fetchMock)!.url
    expect(url).toContain('keep=1')
    expect(url).not.toContain('dropUndef')
    expect(url).not.toContain('dropNull')
    expect(url).not.toContain('dropEmpty')
  })
})
