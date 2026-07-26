import { type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppLayout } from './components/AppLayout'
import { LoadingState } from './components/state/LoadingState'
import AuditPage from './pages/AuditPage'
import DashboardPage from './pages/DashboardPage'
import DeviceDetailPage from './pages/DeviceDetailPage'
import FieldPage from './pages/FieldPage'
import HypothesesPage from './pages/HypothesesPage'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import PlanningPage from './pages/PlanningPage'
import SimulationPage from './pages/SimulationPage'

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
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/hypotheses" element={<HypothesesPage />} />
        <Route path="/planning" element={<PlanningPage />} />
        <Route path="/simulation" element={<SimulationPage />} />
        <Route path="/field" element={<FieldPage />} />
        <Route path="/devices/:id" element={<DeviceDetailPage />} />
        <Route path="/audit" element={<AuditPage />} />
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
