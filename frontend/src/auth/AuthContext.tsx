import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, clearToken, getToken } from '../api/client'
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const hasToken = !!getToken()

  const meQuery = useQuery<User>({
    queryKey: AUTH_QUERY_KEY,
    queryFn: async () => {
      try {
        return await api.getMe()
      } catch (err) {
        clearToken()
        throw err
      }
    },
    enabled: hasToken,
    retry: false,
    staleTime: Infinity,
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
