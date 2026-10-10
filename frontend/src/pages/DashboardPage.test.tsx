import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DashboardPage from './DashboardPage'

const state = vi.hoisted(() => ({ role: 'admin' }))
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { role: state.role } }) }))
vi.mock('../api/client', () => ({ api: { getIncidents: () => Promise.reject(new Error('Unavailable')) } }))
vi.mock('../components/MeshOverview', () => ({ MeshOverview: () => <p>Mesh feed</p> }))
vi.mock('../components/ThermalPanel', () => ({ ThermalPanel: () => <p>Thermal feed</p> }))
vi.mock('../components/DronePanel', () => ({ DronePanel: () => <p>Drone controls</p> }))
vi.mock('./IncidentDashboard', () => ({ default: () => <p>Situation workspace</p> }))
vi.mock('./SimulationPage', () => ({ default: () => <p>Digital twin workspace</p> }))

function mount() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DashboardPage /></QueryClientProvider>)
}
afterEach(() => { cleanup(); state.role = 'admin' })

describe('unified dashboard', () => {
  it('keeps field feeds available when the platform fails and switches workspace', async () => {
    mount()
    expect(await screen.findByText('Platform unavailable')).toBeInTheDocument()
    expect(screen.getByText('Mesh feed')).toBeInTheDocument()
    expect(screen.getByText('Thermal feed')).toBeInTheDocument()
    expect(screen.getByText('Drone controls')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Digital twin' }))
    expect(await screen.findByText('Digital twin workspace')).toBeInTheDocument()
  })
  it('does not mount detailed field feeds for viewers', () => {
    state.role = 'viewer'
    mount()
    expect(screen.queryByText('Mesh feed')).not.toBeInTheDocument()
    expect(screen.queryByText('Thermal feed')).not.toBeInTheDocument()
    expect(screen.queryByText('Drone controls')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Survivor map' })).not.toBeInTheDocument()
  })
})
