import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import FieldResponder from './pages/FieldResponder'
import Communications from './pages/Communications'
import IncidentDetail from './pages/IncidentDetail'
import Incidents from './pages/Incidents'
import Reports from './pages/Reports'
import CommandCenter from './pages/CommandCenter'
import Settings from './pages/Settings'
import Tasks from './pages/Tasks'
import Map from './pages/Map'
import Shelters from './pages/Shelters'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,       // 15s — matches polling interval in DESIGN §11
      refetchInterval: 15_000,
      retry: 1,
    },
  },
})

// Guard: redirect to /login if not authenticated
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-gray-400 text-sm animate-pulse">Loading…</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <>{children}</>
}

// Guard: redirect authenticated users away from /login
function PublicOnly({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-gray-400 text-sm animate-pulse">Loading…</div>
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route
              path="/login"
              element={
                <PublicOnly>
                  <Login />
                </PublicOnly>
              }
            />
            {/* Existing pages have their own full-screen layouts — NOT wrapped in <Layout> */}
            <Route
              path="/dashboard"
              element={
                <RequireAuth>
                  <Dashboard />
                </RequireAuth>
              }
            />
            <Route
              path="/field"
              element={
                <RequireAuth>
                  <FieldResponder />
                </RequireAuth>
              }
            />
            {/* New pages ported from p4 — wrapped in shared <Layout> (sidebar + header) */}
            <Route
              path="/command-center"
              element={
                <RequireAuth>
                  <Layout>
                    <CommandCenter />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/communications"
              element={
                <RequireAuth>
                  <Layout>
                    <Communications />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/incidents"
              element={
                <RequireAuth>
                  <Layout>
                    <Incidents />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/incidents/:id"
              element={
                <RequireAuth>
                  <Layout>
                    <IncidentDetail />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/map"
              element={
                <RequireAuth>
                  <Layout>
                    <Map />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/reports"
              element={
                <RequireAuth>
                  <Layout>
                    <Reports />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/settings"
              element={
                <RequireAuth>
                  <Layout>
                    <Settings />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/shelters"
              element={
                <RequireAuth>
                  <Layout>
                    <Shelters />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/tasks"
              element={
                <RequireAuth>
                  <Layout>
                    <Tasks />
                  </Layout>
                </RequireAuth>
              }
            />
            {/* Default: send to dashboard (RequireAuth will redirect to /login if needed) */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
