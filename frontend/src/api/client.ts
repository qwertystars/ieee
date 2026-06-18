// Typed API client (DESIGN §8 — all endpoints under /api)
// Auth token stored in memory + localStorage fallback

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import type {
  TokenResponse,
  UserRead,
  DisasterEventRead,
  DisasterEventCreate,
  DataSourceRead,
  NormalizedObservationRead,
  IncidentReportRead,
  IncidentReportCreate,
  AreaAssessmentRead,
  RecommendationRead,
  TaskRead,
  TaskCreate,
  TaskUpdate,
  ShelterRead,
  RoadStatusRead,
  ResponseTeamRead,
  DashboardSummary,
  MapLayersResponse,
  AlertRead,
  AuditLogRead,
  PaginatedParams,
  SituationReportRequest,
} from '../types'

// ── Token store (memory-first, localStorage fallback) ───────────────────────

let _token: string | null = null

export const tokenStore = {
  get(): string | null {
    return _token ?? localStorage.getItem('auth_token')
  },
  set(token: string) {
    _token = token
    localStorage.setItem('auth_token', token)
  },
  clear() {
    _token = null
    localStorage.removeItem('auth_token')
  },
}

// ── Axios instance ───────────────────────────────────────────────────────────

const http: AxiosInstance = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      tokenStore.clear()
      // Let callers / AuthContext handle redirect
    }
    return Promise.reject(err)
  },
)

// ── Helper ───────────────────────────────────────────────────────────────────

function paginationParams(p?: PaginatedParams): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  if (p?.limit !== undefined) out['limit'] = p.limit
  if (p?.offset !== undefined) out['offset'] = p.offset
  if (p?.bbox) out['bbox'] = p.bbox
  return out
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  async login(email: string, password: string): Promise<TokenResponse> {
    // FastAPI OAuth2PasswordRequestForm expects form-encoded
    const form = new URLSearchParams({ username: email, password })
    const res = await http.post<TokenResponse>('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return res.data
  },

  async logout(): Promise<void> {
    await http.post('/auth/logout').catch(() => {})
    tokenStore.clear()
  },

  async me(): Promise<UserRead> {
    const res = await http.get<UserRead>('/auth/me')
    return res.data
  },
}

// ── Events ────────────────────────────────────────────────────────────────────

export const eventsApi = {
  async list(params?: PaginatedParams): Promise<DisasterEventRead[]> {
    const res = await http.get<DisasterEventRead[]>('/events', { params: paginationParams(params) })
    return res.data
  },

  async create(data: DisasterEventCreate): Promise<DisasterEventRead> {
    const res = await http.post<DisasterEventRead>('/events', data)
    return res.data
  },

  async get(id: string): Promise<DisasterEventRead> {
    const res = await http.get<DisasterEventRead>(`/events/${id}`)
    return res.data
  },

  async patch(id: string, data: Partial<DisasterEventCreate>): Promise<DisasterEventRead> {
    const res = await http.patch<DisasterEventRead>(`/events/${id}`, data)
    return res.data
  },
}

// ── Data Sources ──────────────────────────────────────────────────────────────

export const dataSourcesApi = {
  async list(params?: PaginatedParams): Promise<DataSourceRead[]> {
    const res = await http.get<DataSourceRead[]>('/data-sources', { params: paginationParams(params) })
    return res.data
  },

  async create(data: Partial<DataSourceRead>): Promise<DataSourceRead> {
    const res = await http.post<DataSourceRead>('/data-sources', data)
    return res.data
  },

  async patch(id: string, data: Partial<DataSourceRead>): Promise<DataSourceRead> {
    const res = await http.patch<DataSourceRead>(`/data-sources/${id}`, data)
    return res.data
  },
}

// ── Observations ───────────────────────────────────────────────────────────────

export const observationsApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<NormalizedObservationRead[]> {
    const res = await http.get<NormalizedObservationRead[]>(`/events/${eventId}/observations`, {
      params: paginationParams(params),
    })
    return res.data
  },

  async create(eventId: string, data: Partial<NormalizedObservationRead>): Promise<NormalizedObservationRead> {
    const res = await http.post<NormalizedObservationRead>(`/events/${eventId}/observations`, data)
    return res.data
  },
}

// ── Reports ────────────────────────────────────────────────────────────────────

export const reportsApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<IncidentReportRead[]> {
    const res = await http.get<IncidentReportRead[]>(`/events/${eventId}/reports`, {
      params: paginationParams(params),
    })
    return res.data
  },

  async create(eventId: string, data: IncidentReportCreate): Promise<IncidentReportRead> {
    const res = await http.post<IncidentReportRead>(`/events/${eventId}/reports`, data)
    return res.data
  },

  async get(id: string): Promise<IncidentReportRead> {
    const res = await http.get<IncidentReportRead>(`/reports/${id}`)
    return res.data
  },

  async verify(id: string, data: { verification_status: string; confidence_score?: number }): Promise<IncidentReportRead> {
    const res = await http.patch<IncidentReportRead>(`/reports/${id}/verify`, data)
    return res.data
  },
}

// ── Areas ──────────────────────────────────────────────────────────────────────

export const areasApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<AreaAssessmentRead[]> {
    const res = await http.get<AreaAssessmentRead[]>(`/events/${eventId}/areas`, {
      params: paginationParams(params),
    })
    return res.data
  },

  async get(id: string): Promise<AreaAssessmentRead> {
    const res = await http.get<AreaAssessmentRead>(`/areas/${id}`)
    return res.data
  },
}

// ── Recommendations ────────────────────────────────────────────────────────────

export const recommendationsApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<RecommendationRead[]> {
    const res = await http.get<RecommendationRead[]>(`/events/${eventId}/recommendations`, {
      params: paginationParams(params),
    })
    return res.data
  },

  async approve(eventId: string, id: string): Promise<RecommendationRead> {
    const res = await http.post<RecommendationRead>(`/events/${eventId}/recommendations/${id}/approve`)
    return res.data
  },

  async dismiss(eventId: string, id: string): Promise<RecommendationRead> {
    const res = await http.post<RecommendationRead>(`/events/${eventId}/recommendations/${id}/dismiss`)
    return res.data
  },
}

// ── Tasks ──────────────────────────────────────────────────────────────────────

export const tasksApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<TaskRead[]> {
    const res = await http.get<TaskRead[]>(`/events/${eventId}/tasks`, {
      params: paginationParams(params),
    })
    return res.data
  },

  async create(eventId: string, data: TaskCreate): Promise<TaskRead> {
    const res = await http.post<TaskRead>(`/events/${eventId}/tasks`, data)
    return res.data
  },

  async patch(id: string, data: TaskUpdate): Promise<TaskRead> {
    const res = await http.patch<TaskRead>(`/tasks/${id}`, data)
    return res.data
  },
}

// ── Shelters ────────────────────────────────────────────────────────────────────

export const sheltersApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<ShelterRead[]> {
    const res = await http.get<ShelterRead[]>(`/events/${eventId}/shelters`, {
      params: paginationParams(params),
    })
    return res.data
  },

  async patchStatus(id: string, data: { status: string; current_occupancy?: number }): Promise<ShelterRead> {
    const res = await http.patch<ShelterRead>(`/shelters/${id}/status`, data)
    return res.data
  },
}

// ── Roads ───────────────────────────────────────────────────────────────────────

export const roadsApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<RoadStatusRead[]> {
    const res = await http.get<RoadStatusRead[]>(`/events/${eventId}/roads/status`, {
      params: paginationParams(params),
    })
    return res.data
  },

  async patchStatus(
    id: string,
    data: { status: string; reason?: string; confidence_score?: number },
  ): Promise<RoadStatusRead> {
    const res = await http.patch<RoadStatusRead>(`/roads/${id}/status`, data)
    return res.data
  },
}

// ── Teams ────────────────────────────────────────────────────────────────────────

export const teamsApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<ResponseTeamRead[]> {
    const res = await http.get<ResponseTeamRead[]>(`/events/${eventId}/teams`, {
      params: paginationParams(params),
    })
    return res.data
  },

  async patchLocation(
    id: string,
    data: { current_location: { type: 'Point'; coordinates: [number, number] } },
  ): Promise<ResponseTeamRead> {
    const res = await http.patch<ResponseTeamRead>(`/teams/${id}/location`, data)
    return res.data
  },

  async patchStatus(id: string, data: { status: string }): Promise<ResponseTeamRead> {
    const res = await http.patch<ResponseTeamRead>(`/teams/${id}/status`, data)
    return res.data
  },
}

// ── Dashboard ─────────────────────────────────────────────────────────────────────

export const dashboardApi = {
  async summary(eventId: string): Promise<DashboardSummary> {
    const res = await http.get<DashboardSummary>(`/events/${eventId}/dashboard-summary`)
    return res.data
  },

  async mapLayers(eventId: string, params?: PaginatedParams): Promise<MapLayersResponse> {
    const res = await http.get<MapLayersResponse>(`/events/${eventId}/map-layers`, {
      params: paginationParams(params),
    })
    return res.data
  },
}

// ── Alerts ────────────────────────────────────────────────────────────────────────

export const alertsApi = {
  async list(eventId: string): Promise<AlertRead[]> {
    const res = await http.get<AlertRead[]>(`/events/${eventId}/alerts`)
    return res.data
  },
}

// ── Situation Report ───────────────────────────────────────────────────────────────

export const situationReportApi = {
  async generate(eventId: string, req: SituationReportRequest, config?: AxiosRequestConfig): Promise<Blob | string> {
    const res = await http.post(`/events/${eventId}/situation-report`, req, {
      responseType: req.format === 'pdf' ? 'blob' : 'text',
      ...config,
    })
    return res.data as Blob | string
  },
}

// ── Audit ─────────────────────────────────────────────────────────────────────────

export const auditApi = {
  async list(eventId: string, params?: PaginatedParams): Promise<AuditLogRead[]> {
    const res = await http.get<AuditLogRead[]>(`/events/${eventId}/audit-logs`, {
      params: paginationParams(params),
    })
    return res.data
  },
}

// ── Ingestion (manual trigger) ─────────────────────────────────────────────────────

export const ingestionApi = {
  async trigger(eventId: string, sourceType: string): Promise<{ observations_created: number }> {
    const res = await http.post<{ observations_created: number }>(`/events/${eventId}/ingest/${sourceType}`)
    return res.data
  },
}

export default http
