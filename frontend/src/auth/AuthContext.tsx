import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { authApi, tokenStore } from '../api/client'
import type { UserRead } from '../types'

interface AuthState {
  user: UserRead | null
  token: string | null
  isLoading: boolean
  isAuthenticated: boolean
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: tokenStore.get(),
    isLoading: true,
    isAuthenticated: false,
  })

  // On mount: if token exists, verify it by fetching /auth/me
  useEffect(() => {
    const storedToken = tokenStore.get()
    if (!storedToken) {
      setState((s) => ({ ...s, isLoading: false }))
      return
    }
    authApi
      .me()
      .then((user) => {
        setState({ user, token: storedToken, isLoading: false, isAuthenticated: true })
      })
      .catch(() => {
        tokenStore.clear()
        setState({ user: null, token: null, isLoading: false, isAuthenticated: false })
      })
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password)
    tokenStore.set(access_token)
    const user = await authApi.me()
    setState({ user, token: access_token, isLoading: false, isAuthenticated: true })
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout()
    setState({ user: null, token: null, isLoading: false, isAuthenticated: false })
  }, [])

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
