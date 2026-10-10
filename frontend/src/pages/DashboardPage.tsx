import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { MeshOverview } from '../components/MeshOverview'
import { ThermalPanel } from '../components/ThermalPanel'
import { DronePanel } from '../components/DronePanel'
import { OperationsPanel } from '../components/OperationsPanel'
import { LoadingState } from '../components/state'

const IncidentDashboard = lazy(() => import('./IncidentDashboard'))
const RescuePage = lazy(() => import('./RescuePage'))
const PlanningPage = lazy(() => import('./PlanningPage'))
const SimulationPage = lazy(() => import('./SimulationPage'))
const FieldPage = lazy(() => import('./FieldPage'))
const HypothesesPage = lazy(() => import('./HypothesesPage'))
const AuditPage = lazy(() => import('./AuditPage'))
const RouteSandbox = lazy(() => import('../components/RouteSandbox'))

const WORKSPACES = {
  situation: { label: 'Situation map', component: IncidentDashboard },
  rescue: { label: 'Survivor map', component: RescuePage },
  planning: { label: 'Planning & dispatch', component: PlanningPage },
  routes: { label: 'Route sandbox', component: RouteSandbox },
  simulation: { label: 'Digital twin', component: SimulationPage },
  field: { label: 'Field operations', component: FieldPage },
  hypotheses: { label: 'AI hypotheses', component: HypothesesPage },
  audit: { label: 'Audit trail', component: AuditPage },
}
type Workspace = keyof typeof WORKSPACES

export default function DashboardPage() {
  const { user } = useAuth()
  const fieldAccess = (import.meta.env.DEV && !user) || (!!user && user.role !== 'viewer')
  const [workspace, setWorkspace] = useState<Workspace>('situation')
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: ({ signal }) => api.getIncidents(signal), refetchInterval: 10000 })
  const incident = incidents.data?.incidents[0]
  const WorkspaceComponent = WORKSPACES[workspace].component

  return (
    <div className="mx-auto max-w-[1800px] space-y-6 p-4 text-slate-100 md:p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="mb-2 text-xs uppercase tracking-[0.25em] text-cyan-400">ResQnet · unified operations</p><h1 className="text-2xl font-semibold md:text-3xl">Rescue command center</h1><p className="mt-2 text-sm text-slate-400">Situation awareness, field signals, thermal intelligence and drone control.</p></div>
        <span role="status" className="rounded-full border border-slate-700 px-4 py-2 text-xs text-slate-300">{incidents.isPending ? 'Connecting to platform…' : incidents.isError ? 'Platform unavailable' : incident ? incident.title : 'No active incident'}</span>
      </header>

      <OperationsPanel title="Operations workspace" status="All tools in one dashboard">
        <nav className="flex flex-wrap gap-2" aria-label="Dashboard workspaces">
          {(Object.keys(WORKSPACES) as Workspace[]).filter(key => fieldAccess || key !== 'rescue').map(key => <button key={key} type="button" aria-pressed={workspace === key} aria-controls="operations-workspace" onClick={() => setWorkspace(key)} className={`rounded-lg px-4 py-2 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-cyan-400 ${workspace === key ? 'bg-cyan-700 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>{WORKSPACES[key].label}</button>)}
        </nav>
      </OperationsPanel>

      <section id="operations-workspace" aria-label={WORKSPACES[workspace].label} className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
        <div className="border-b border-slate-800 px-5 py-3 text-sm font-semibold">{WORKSPACES[workspace].label}</div>
        <Suspense fallback={<div className="p-6"><LoadingState message="Loading workspace…" /></div>}><WorkspaceComponent /></Suspense>
      </section>

      {fieldAccess ? <div className="grid items-start gap-4 xl:grid-cols-3"><MeshOverview /><ThermalPanel /><DronePanel /></div>
        : <OperationsPanel title="Field feeds"><p className="text-sm text-slate-400">Detailed survivor, thermal and drone feeds are available to operational roles.</p></OperationsPanel>}
    </div>
  )
}
