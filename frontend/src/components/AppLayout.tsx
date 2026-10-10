import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useOutbox } from '../hooks/useOutbox'
import { LowBandwidthToggle } from './LowBandwidthToggle'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/hypotheses', label: 'Hypotheses' },
  { to: '/planning', label: 'Planning' },
  { to: '/simulation', label: 'Simulation' },
  { to: '/rescue', label: 'Rescue' },
  { to: '/field', label: 'Field' },
  { to: '/audit', label: 'Audit' },
] as const

export function AppLayout() {
  const { user, logout } = useAuth()
  const { pendingCount, failedCount, conflictCount, isOnline } = useOutbox()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/dashboard', { replace: true })
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-950">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 bg-gray-900 px-4 py-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <span className="text-sm font-bold text-gray-100">ResQNet-SAGE</span>
          <nav className="flex flex-wrap items-center gap-1" aria-label="Main navigation">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                  }`
                }
                aria-label={item.label}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <LowBandwidthToggle />
          <span
            role="status"
            aria-label={isOnline ? 'Network online' : 'Network offline'}
            className={`flex items-center gap-1.5 text-xs ${isOnline ? 'text-green-400' : 'text-red-400'}`}
          >
            <span
              className={`h-2 w-2 rounded-full ${isOnline ? 'bg-green-400' : 'bg-red-400'}`}
              aria-hidden="true"
            />
            {isOnline ? 'Online' : 'Offline'}
          </span>
          {pendingCount > 0 ? (
            <span
              role="status"
              data-testid="pending-badge"
              aria-label={`${pendingCount} pending offline change${pendingCount === 1 ? '' : 's'} queued for sync`}
              className="rounded-full bg-amber-600 px-2 py-0.5 text-[10px] font-medium text-white"
            >
              {pendingCount} pending
            </span>
            ) : (
            <span
              role="status"
              data-testid="synced-badge"
              aria-label="All changes synced"
              className="rounded-full bg-green-600 px-2 py-0.5 text-[10px] font-medium text-white"
            >
              Synced
            </span>
            )}
          {conflictCount > 0 && (
            <span
              role="status"
              data-testid="conflict-badge"
              aria-label={`${conflictCount} sync conflict${conflictCount === 1 ? '' : 's'} require manual resolution`}
              className="rounded-full bg-red-700 px-2 py-0.5 text-[10px] font-medium text-white"
            >
              Conflict: manual resolution required
            </span>
          )}
          {failedCount > 0 && (
            <span
              role="status"
              data-testid="failed-badge"
              aria-label={`${failedCount} offline change${failedCount === 1 ? '' : 's'} failed and require retry`}
              className="rounded-full bg-red-900 px-2 py-0.5 text-[10px] font-medium text-red-200"
            >
              Sync failed: retry required
            </span>
          )}
          {user && (
            <span className="text-xs text-gray-500" aria-label="Current user">
              {user.email}
              <span className="ml-1.5 rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-400">
                {user.role}
              </span>
            </span>
          )}
          <button
            onClick={handleLogout}
            className="rounded-md border border-gray-700 px-3 py-1 text-xs text-gray-300 transition-colors hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Sign out"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
