// Typed API client — JWT in memory + localStorage, automatic header injection.
// Endpoints mirror DESIGN.md §8 and backend/app/api/routes/.

import type {
  AlertList,
  AuditLogList,
  AuditVerifyResponse,
  CreateTaskRequest,
  DegradationSummary,
  EntityFeatureCollection,
  FeedHealthResponse,
  HypothesisList,
  IncidentList,
  InjectFaultRequest,
  InjectFaultResponse,
  ModifyAlertRequest,
  ObservationCollection,
  ProvenanceResponse,
  SimulatorStartRequest,
  SimulatorStartResponse,
  SimulatorStatus,
  SituationReport,
  Task,
  TaskList,
  TokenResponse,
  UpdateEntityRequest,
  UpdateTaskStatusRequest,
  User,
} from './types'
import { clearToken, getToken, setToken } from './token'
import { addToOutbox, inferPriority } from '../lib/outbox'

const DEFAULT_BASE = 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public path: string,
  ) {
    super(`[${status}] ${detail}`)
    this.name = 'ApiError'
  }
}

export { clearToken, getToken, setToken }

function baseUrl(): string {
  const env = import.meta.env.VITE_API_BASE
  return typeof env === 'string' && env.length > 0 ? env : DEFAULT_BASE
}

type Query = Record<string, string | number | boolean | undefined | null>

function buildUrl(path: string, query?: Query): string {
  const url = new URL(baseUrl() + path)
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
    }
  }
  return url.toString()
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE' | 'PUT'
  body?: unknown
  query?: Query
  form?: URLSearchParams
  signal?: AbortSignal
  headers?: Record<string, string>
  _skipOutbox?: boolean
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, form, signal, headers: extraHeaders, _skipOutbox } = opts

  // Route mutations to outbox when offline (GETs and auth excluded).
  if (!_skipOutbox && method !== 'GET' && typeof navigator !== 'undefined' && !navigator.onLine) {
    if (path.startsWith('/api/auth/')) {
      throw new ApiError(0, 'offline — authentication required', path)
    }
    try {
      const priority = inferPriority(path, method)
      await addToOutbox(path, method, body, priority)
      return undefined as T
    } catch {
      throw new ApiError(0, 'offline and outbox unavailable', path)
    }
  }

  const headers: Record<string, string> = { Accept: 'application/json' }
  if (extraHeaders) Object.assign(headers, extraHeaders)
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  let payload: BodyInit | undefined
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = form
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let res: Response
  try {
    res = await fetch(buildUrl(path, query), { method, headers, body: payload, signal })
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : 'network error', path)
  }

  if (res.status === 204) return undefined as T

  const text = await res.text()
  const data = text ? safeParse(text) : null

  if (!res.ok) {
    const detail = extractDetail(data) ?? res.statusText ?? 'request failed'
    throw new ApiError(res.status, detail, path)
  }
  return data as T
}

function safeParse(text: string): unknown {
  try { return JSON.parse(text) } catch { return text }
}

function extractDetail(data: unknown): string | null {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = (data as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map(String).join('; ')
  }
  return typeof data === 'string' && data.length > 0 ? data : null
}

// --- Auth -----------------------------------------------------------------

export const api = {
  async login(email: string, password: string): Promise<TokenResponse> {
    const form = new URLSearchParams()
    form.set('username', email)
    form.set('password', password)
    const res = await request<TokenResponse>('/api/auth/login', {
      method: 'POST',
      form,
    })
    setToken(res.access_token)
    return res
  },

  async getMe(signal?: AbortSignal): Promise<User> {
    return request<User>('/api/auth/me', { signal })
  },

  async logout(): Promise<void> {
    try {
      await request<void>('/api/auth/logout', { method: 'POST' })
    } finally {
      clearToken()
    }
  },

  // --- Incidents / observations -------------------------------------------

  async getIncidents(signal?: AbortSignal): Promise<IncidentList> {
    return request<IncidentList>('/api/incidents', { signal })
  },

  async getObservations(
    incidentId: string,
    signal?: AbortSignal,
  ): Promise<ObservationCollection> {
    return request<ObservationCollection>('/api/observations', {
      query: { incident_id: incidentId },
      signal,
    })
  },

  async getHypotheses(incidentId: string, signal?: AbortSignal): Promise<HypothesisList> {
    return request<HypothesisList>(
      `/api/incidents/${encodeURIComponent(incidentId)}/hypotheses`,
      { signal },
    )
  },

  async getAlerts(incidentId: string, signal?: AbortSignal): Promise<AlertList> {
    return request<AlertList>(
      `/api/incidents/${encodeURIComponent(incidentId)}/alerts`,
      { signal },
    )
  },

  async getTasks(incidentId: string, signal?: AbortSignal): Promise<TaskList> {
    return request<TaskList>(
      `/api/incidents/${encodeURIComponent(incidentId)}/tasks`,
      { signal },
    )
  },

  async getSituationReport(
    incidentId: string,
    signal?: AbortSignal,
  ): Promise<SituationReport> {
    return request<SituationReport>(
      `/api/incidents/${encodeURIComponent(incidentId)}/situation-report`,
      { signal },
    )
  },

  async getEntities(
    incidentId: string,
    type?: string,
    signal?: AbortSignal,
  ): Promise<EntityFeatureCollection> {
    return request<EntityFeatureCollection>(
      `/api/incidents/${encodeURIComponent(incidentId)}/entities`,
      { query: { type }, signal },
    )
  },

  async getAuditLogs(incidentId: string, signal?: AbortSignal): Promise<AuditLogList> {
    return request<AuditLogList>(
      `/api/incidents/${encodeURIComponent(incidentId)}/audit-logs`,
      { signal },
    )
  },

  // --- Simulator ----------------------------------------------------------

  async simulatorStatus(signal?: AbortSignal): Promise<SimulatorStatus> {
    return request<SimulatorStatus>('/api/simulator/status', { signal })
  },

  async simulatorStart(
    body: SimulatorStartRequest,
    signal?: AbortSignal,
  ): Promise<SimulatorStartResponse> {
    return request<SimulatorStartResponse>('/api/simulator/start', {
      method: 'POST',
      body,
      signal,
    })
  },

  async simulatorStop(signal?: AbortSignal): Promise<void> {
    return request<void>('/api/simulator/stop', { method: 'POST', signal })
  },

  async simulatorPause(signal?: AbortSignal): Promise<void> {
    return request<void>('/api/simulator/pause', { method: 'POST', signal })
  },

  async simulatorResume(signal?: AbortSignal): Promise<void> {
    return request<void>('/api/simulator/resume', { method: 'POST', signal })
  },

  async simulatorSetSpeed(speed: number, signal?: AbortSignal): Promise<void> {
    return request<void>('/api/simulator/set-speed', {
      method: 'POST',
      body: { speed },
      signal,
    })
  },

  async simulatorInjectFault(
    body: InjectFaultRequest,
    signal?: AbortSignal,
  ): Promise<InjectFaultResponse> {
    return request<InjectFaultResponse>('/api/simulator/inject-fault', {
      method: 'POST',
      body,
      signal,
    })
  },

  // --- Alert review -------------------------------------------------------

  async approveAlert(
    incidentId: string,
    alertId: string,
    rationale?: string,
    signal?: AbortSignal,
  ): Promise<unknown> {
    return request<unknown>(
      `/api/incidents/${encodeURIComponent(incidentId)}/alerts/${encodeURIComponent(alertId)}/approve`,
      { method: 'POST', body: { review_rationale: rationale ?? '' }, signal },
    )
  },

  async dismissAlert(
    incidentId: string,
    alertId: string,
    rationale: string,
    signal?: AbortSignal,
  ): Promise<unknown> {
    return request<unknown>(
      `/api/incidents/${encodeURIComponent(incidentId)}/alerts/${encodeURIComponent(alertId)}/dismiss`,
      { method: 'POST', body: { review_rationale: rationale }, signal },
    )
  },

  async modifyAlert(
    incidentId: string,
    alertId: string,
    body: ModifyAlertRequest,
    signal?: AbortSignal,
  ): Promise<unknown> {
    return request<unknown>(
      `/api/incidents/${encodeURIComponent(incidentId)}/alerts/${encodeURIComponent(alertId)}/modify`,
      { method: 'POST', body, signal },
    )
  },

  // --- Tasks --------------------------------------------------------------

  async createTask(
    incidentId: string,
    body: CreateTaskRequest,
    signal?: AbortSignal,
  ): Promise<Task> {
    return request<Task>(
      `/api/incidents/${encodeURIComponent(incidentId)}/tasks`,
      { method: 'POST', body, signal },
    )
  },

  async assignTask(
    incidentId: string,
    taskId: string,
    signal?: AbortSignal,
  ): Promise<Task> {
    return request<Task>(
      `/api/incidents/${encodeURIComponent(incidentId)}/tasks/${encodeURIComponent(taskId)}/assign`,
      { method: 'POST', signal },
    )
  },

  async updateTaskStatus(
    taskId: string,
    body: UpdateTaskStatusRequest,
    signal?: AbortSignal,
  ): Promise<Task> {
    return request<Task>(
      `/api/tasks/${encodeURIComponent(taskId)}`,
      { method: 'PATCH', body, signal },
    )
  },

  // --- Entities ----------------------------------------------------------

  async updateEntity(
    incidentId: string,
    entityType: string,
    entityId: string,
    body: UpdateEntityRequest,
    signal?: AbortSignal,
  ): Promise<unknown> {
    return request<unknown>(
      `/api/incidents/${encodeURIComponent(incidentId)}/entities/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
      { method: 'PATCH', body, signal },
    )
  },

  // --- Audit / provenance ------------------------------------------------

  async getAuditVerify(signal?: AbortSignal): Promise<AuditVerifyResponse> {
    return request<AuditVerifyResponse>('/api/audit/verify', { signal })
  },

  async getDecisionProvenance(
    recordId: string,
    signal?: AbortSignal,
  ): Promise<ProvenanceResponse> {
    return request<ProvenanceResponse>(
      `/api/decisions/${encodeURIComponent(recordId)}/provenance`,
      { signal },
    )
  },

  async getFeedHealth(
    incidentId: string,
    signal?: AbortSignal,
  ): Promise<FeedHealthResponse> {
    return request<FeedHealthResponse>(
      `/api/incidents/${encodeURIComponent(incidentId)}/feed-health`,
      { signal },
    )
  },

  async getDegradationSummary(
    incidentId: string,
    signal?: AbortSignal,
  ): Promise<DegradationSummary> {
    return request<DegradationSummary>(
      `/api/incidents/${encodeURIComponent(incidentId)}/degradation-summary`,
      { signal },
    )
  },
} as const

export type Api = typeof api
