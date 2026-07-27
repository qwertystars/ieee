// Unit tests for AuthContext — real provider state transitions with the
// api module mocked. Exercises: initial load (token present/absent),
// login→getMe→setUser chain, logout→clearUser, and the useAuth guard.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import type { ReactNode } from 'react'
import { AuthProvider, useAuth } from './AuthContext'
import type { User } from '../api/types'

const MOCK_USER: User = {
  id: 'u-1',
  email: 'admin@demo.disaster',
  role: 'admin',
  org_id: 'org-1',
}

// Mock the api/client module. AuthContext imports { api, clearToken, getToken }.
vi.mock('../api/client', () => ({
  api: {
    login: vi.fn(),
    getMe: vi.fn(),
    logout: vi.fn(),
  },
  clearToken: vi.fn(),
  getToken: vi.fn(),
  setToken: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public status: number, public detail: string, public path: string) {
      super(`[${status}] ${detail}`)
      this.name = 'ApiError'
    }
  },
}))

import { api } from '../api/client'

// Helper: a consumer component that exposes the context value via DOM.
// Buttons are async-aware so rejections don't become unhandled promise rejections.
function Consumer() {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="user">{auth.user?.email ?? 'none'}</span>
      <span data-testid="loading">{String(auth.loading)}</span>
      <span data-testid="authenticated">{String(auth.isAuthenticated)}</span>
      <button
        data-testid="login-btn"
        onClick={() => auth.login('admin@demo.disaster', 'demo1234').catch(() => {})}
      >
        login
      </button>
      <button
        data-testid="logout-btn"
        onClick={() => auth.logout().catch(() => {})}
      >
        logout
      </button>
    </div>
  )
}

function renderWithProvider(node: ReactNode) {
  return render(<AuthProvider>{node}</AuthProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.login).mockReset()
  vi.mocked(api.getMe).mockReset()
  vi.mocked(api.logout).mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AuthProvider — initial mount', () => {
  it('sets loading=false immediately when no token is stored', async () => {
    const { getToken } = await import('../api/client')
    vi.mocked(getToken).mockReturnValue(null)

    renderWithProvider(<Consumer />)

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('user').textContent).toBe('none')
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    // getMe must NOT be called when there is no token.
    expect(api.getMe).not.toHaveBeenCalled()
  })

  it('fetches the current user when a token is present and sets loading=false on success', async () => {
    const { getToken } = await import('../api/client')
    vi.mocked(getToken).mockReturnValue('jwt-existing')
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)

    renderWithProvider(<Consumer />)

    // While the getMe promise is in flight, loading is true.
    expect(screen.getByTestId('loading').textContent).toBe('true')

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('user').textContent).toBe('admin@demo.disaster')
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(api.getMe).toHaveBeenCalledTimes(1)
  })

  it('clears the token and stays unauthenticated when getMe fails', async () => {
    const { getToken, clearToken } = await import('../api/client')
    vi.mocked(getToken).mockReturnValue('jwt-stale')
    vi.mocked(api.getMe).mockRejectedValue(new Error('401'))

    renderWithProvider(<Consumer />)

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('user').textContent).toBe('none')
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    // Stale token must be cleared so the next mount doesn't retry.
    expect(clearToken).toHaveBeenCalled()
  })
})

describe('AuthProvider — login flow', () => {
  it('calls api.login then api.getMe and exposes the user', async () => {
    const { getToken } = await import('../api/client')
    vi.mocked(getToken).mockReturnValue(null)
    vi.mocked(api.login).mockResolvedValue({ access_token: 'jwt-new', token_type: 'bearer' })
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)

    renderWithProvider(<Consumer />)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    await act(async () => {
      screen.getByTestId('login-btn').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('admin@demo.disaster')
    })
    expect(screen.getByTestId('authenticated').textContent).toBe('true')

    // login must be called with the credentials from the consumer.
    expect(api.login).toHaveBeenCalledWith('admin@demo.disaster', 'demo1234')
    // getMe is called once after login to hydrate the user.
    expect(api.getMe).toHaveBeenCalledTimes(1)
  })

  it('stays unauthenticated when login throws', async () => {
    const { getToken } = await import('../api/client')
    vi.mocked(getToken).mockReturnValue(null)
    vi.mocked(api.login).mockRejectedValue(
      Object.assign(new Error('401'), { name: 'ApiError', status: 401, detail: 'bad creds' }),
    )

    renderWithProvider(<Consumer />)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    await act(async () => {
      screen.getByTestId('login-btn').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('none')
    })
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    // getMe must NOT be called when login itself fails.
    expect(api.getMe).not.toHaveBeenCalled()
  })
})

describe('AuthProvider — logout flow', () => {
  it('calls api.logout and clears the user from state', async () => {
    const { getToken } = await import('../api/client')
    vi.mocked(getToken).mockReturnValue('jwt-active')
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)
    vi.mocked(api.logout).mockResolvedValue(undefined)

    renderWithProvider(<Consumer />)

    // Wait for initial hydration.
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('admin@demo.disaster')
    })

    await act(async () => {
      screen.getByTestId('logout-btn').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('none')
    })
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(api.logout).toHaveBeenCalledTimes(1)
  })

  it('does NOT clear the user when api.logout rejects (state change is after await)', async () => {
    const { getToken } = await import('../api/client')
    vi.mocked(getToken).mockReturnValue('jwt-active')
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)
    vi.mocked(api.logout).mockRejectedValue(new Error('network down'))

    renderWithProvider(<Consumer />)
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('admin@demo.disaster')
    })

    await act(async () => {
      screen.getByTestId('logout-btn').click()
    })
    // Give the rejected promise a tick to settle.
    await new Promise(r => setTimeout(r, 0))

    // Because setUser(null) is after `await api.logout()`, a rejection
    // means the user remains authenticated — the caller must handle the error.
    expect(screen.getByTestId('user').textContent).toBe('admin@demo.disaster')
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(api.logout).toHaveBeenCalledTimes(1)
  })
})

describe('useAuth — provider guard', () => {
  it('throws when used outside an AuthProvider', () => {
    // Suppress the expected console.error from React's error boundary logging.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Consumer />)).toThrow(/useAuth must be used within an AuthProvider/)
    spy.mockRestore()
  })
})
