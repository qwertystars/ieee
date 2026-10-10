import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, clearToken, getToken } from '../api/client'
import type { User } from '../api/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const AUTH_QUERY_KEY = ['auth-me'] as const

function expiresSoon(token: string | null): boolean {
  if (!token) return true
  try {
    const claims: unknown = JSON.parse(window.atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof claims === 'object' && claims !== null && 'exp' in claims &&
      typeof claims.exp === 'number' && claims.exp * 1000 < Date.now() + 120000
  } catch { return false }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const hasToken = !!getToken()
  const localSession = import.meta.env.DEV && import.meta.env.VITE_LOCAL_DEMO_LOGIN === 'true'

  const meQuery = useQuery<User>({
    queryKey: AUTH_QUERY_KEY,
    queryFn: async () => {
      try {
        if (localSession && expiresSoon(getToken())) {
          await api.login('admin@demo.disaster', 'demo1234')
        }
        try {
          return await api.getMe()
        } catch (err) {
          if (!localSession || !(err instanceof ApiError) || err.status !== 401) throw err
          await api.login('admin@demo.disaster', 'demo1234')
          return await api.getMe()
        }
      } catch (err) {
        clearToken()
        throw err
      }
    },
    enabled: hasToken || localSession,
    retry: false,
    staleTime: localSession ? 60000 : Infinity,
    refetchInterval: localSession ? 60000 : false,
  })

  const user = meQuery.data ?? null
  const loading = meQuery.isLoading

  const login = useCallback(async (email: string, password: string) => {
    await api.login(email, password)
    const u = await api.getMe()
    queryClient.setQueryData(AUTH_QUERY_KEY, u)
  }, [queryClient])

  const logout = useCallback(async () => {
    await api.logout()
    queryClient.setQueryData(AUTH_QUERY_KEY, null)
  }, [queryClient])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: user !== null,
      login,
      logout,
    }),
    [user, loading, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
