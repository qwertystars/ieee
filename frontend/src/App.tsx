import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppLayout } from './components/AppLayout'
import { LoadingState } from './components/state/LoadingState'
import LoginPage from './pages/LoginPage'

const AuditPage = lazy(() => import('./pages/AuditPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const DeviceDetailPage = lazy(() => import('./pages/DeviceDetailPage'))
const FieldPage = lazy(() => import('./pages/FieldPage'))
const HypothesesPage = lazy(() => import('./pages/HypothesesPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))
const PlanningPage = lazy(() => import('./pages/PlanningPage'))
const SimulationPage = lazy(() => import('./pages/SimulationPage'))

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950">
        <LoadingState message="Authenticating…" />
      </div>
    )
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route
          path="/dashboard"
          element={
            <Suspense fallback={<LoadingState />}>
              <DashboardPage />
            </Suspense>
          }
        />
        <Route
          path="/hypotheses"
          element={
            <Suspense fallback={<LoadingState />}>
              <HypothesesPage />
            </Suspense>
          }
        />
        <Route
          path="/planning"
          element={
            <Suspense fallback={<LoadingState />}>
              <PlanningPage />
            </Suspense>
          }
        />
        <Route
          path="/simulation"
          element={
            <Suspense fallback={<LoadingState />}>
              <SimulationPage />
            </Suspense>
          }
        />
        <Route
          path="/field"
          element={
            <Suspense fallback={<LoadingState />}>
              <FieldPage />
            </Suspense>
          }
        />
        <Route
          path="/devices/:id"
          element={
            <Suspense fallback={<LoadingState />}>
              <DeviceDetailPage />
            </Suspense>
          }
        />
        <Route
          path="/audit"
          element={
            <Suspense fallback={<LoadingState />}>
              <AuditPage />
            </Suspense>
          }
        />
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route
        path="*"
        element={
          <Suspense fallback={<LoadingState />}>
            <NotFoundPage />
          </Suspense>
        }
      />
    </Routes>
  )
}
