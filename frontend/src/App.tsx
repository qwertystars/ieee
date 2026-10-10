import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppLayout } from './components/AppLayout'
import { LoadingState } from './components/state/LoadingState'

const AuditPage = lazy(() => import('./pages/AuditPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const DeviceDetailPage = lazy(() => import('./pages/DeviceDetailPage'))
const FieldPage = lazy(() => import('./pages/FieldPage'))
const HypothesesPage = lazy(() => import('./pages/HypothesesPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))
const PlanningPage = lazy(() => import('./pages/PlanningPage'))
const RescuePage = lazy(() => import('./pages/RescuePage'))
const SimulationPage = lazy(() => import('./pages/SimulationPage'))

function ProtectedRoute({ children, operational = false }: { children: ReactNode; operational?: boolean }) {
  const { isAuthenticated, loading, user } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950">
        <LoadingState message="Authenticating…" />
      </div>
    )
  }
  if (!isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }
  if (operational && user?.role === 'viewer') return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

function DashboardEntry() {
  const { loading } = useAuth()
  if (loading) return <div className="flex min-h-screen items-center justify-center bg-slate-950"><LoadingState message="Connecting to the platform…" /></div>
  return <div className="min-h-screen bg-slate-950"><Suspense fallback={<LoadingState />}><DashboardPage /></Suspense></div>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<DashboardEntry />} />
      <Route path="/preview" element={<Navigate to="/dashboard" replace />} />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
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
          path="/rescue"
          element={
            <Suspense fallback={<LoadingState />}>
              <ProtectedRoute operational><RescuePage /></ProtectedRoute>
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
