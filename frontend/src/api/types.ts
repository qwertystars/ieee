// TypeScript mirrors of backend Pydantic schemas (DESIGN.md §8).
// Keep in sync with backend/app/schemas/ and route response shapes.

// Minimal GeoJSON types (avoids adding @types/geojson dependency).
export type GeoJSONGeometry =
  | { type: 'Point'; coordinates: [number, number] }
  | { type: 'LineString'; coordinates: [number, number][] }
  | { type: 'Polygon'; coordinates: [number, number][][] }
  | { type: 'MultiPoint'; coordinates: [number, number][] }
  | { type: 'MultiLineString'; coordinates: [number, number][][] }
  | { type: 'MultiPolygon'; coordinates: [number, number][][][] }
  | { type: 'GeometryCollection'; geometries: GeoJSONGeometry[] }

export interface GeoJSONFeature<P = Record<string, unknown>> {
  type: 'Feature'
  geometry: GeoJSONGeometry | null
  properties: P
}

export interface GeoJSONFeatureCollection<P = Record<string, unknown>> {
  type: 'FeatureCollection'
  features: GeoJSONFeature<P>[]
}

export type Role =
  | 'admin'
  | 'emergency_manager'
  | 'responder_coordinator'
  | 'field_responder'
  | 'shelter_manager'
  | 'viewer'

export interface User {
  id: string
  email: string
  role: Role
  org_id: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface Incident {
  id: string
  org_id: string
  name: string
  status: string
  start_time: number
  end_time?: number | null
  geometry?: GeoJSONGeometry | null
  properties?: Record<string, unknown> | null
  created_at: number
  updated_at: number
}

export interface IncidentList {
  incidents: Incident[]
  count: number
}

export interface Observation {
  id: string
  incident_id: string
  source_id?: string | null
  phenomenon: string
  observed_at: number
  received_at: number
  confidence?: number | null
  properties?: Record<string, unknown> | null
  geometry?: GeoJSONGeometry | null
}

export interface ObservationCollection {
  type: 'FeatureCollection'
  features: GeoJSONFeature<Observation>[]
}

export interface Hypothesis {
  id: string
  incident_id: string
  statement: string
  status: string
  confidence: number
  supports: string[]
  contradicts: string[]
  created_at: number
  updated_at: number
}

export interface HypothesisList {
  hypotheses: Hypothesis[]
  count: number
}

export interface Alert {
  id: string
  incident_id: string
  alert_type: string
  severity: string
  status: string
  recommended_action: string
  rationale?: string | null
  reviewed_by?: string | null
  reviewed_at?: number | null
  created_at: number
  updated_at: number
}

export interface AlertList {
  alerts: Alert[]
  count: number
}

export interface Task {
  id: string
  incident_id: string
  title: string
  status: string
  priority?: string | null
  required_capability?: string | null
  assigned_team_id?: string | null
  geometry?: GeoJSONGeometry | null
  properties?: Record<string, unknown> | null
  created_at: number
  updated_at: number
}

export interface TaskList {
  tasks: Task[]
  count: number
}

export interface SituationReport {
  incident_id: string
  generated_at: number
  summary: string
  observations_count: number
  hazards_count: number
  hypotheses_count: number
  tasks_count: number
  alerts_count: number
  [key: string]: unknown
}

export interface EntityFeatureCollection {
  type: 'FeatureCollection'
  features: GeoJSONFeature[]
}

export interface AuditLog {
  id: string
  ts: number
  actor: string
  action: string
  entity: string
  before?: Record<string, unknown> | null
  after?: Record<string, unknown> | null
  prev_hash: string
  hash: string
}

export interface AuditLogList {
  logs: AuditLog[]
  count: number
}

export interface SimulatorStatus {
  running: boolean
  device_count: number
  devices: SimulatorDevice[]
  started_at?: number | null
  [key: string]: unknown
}

export interface SimulatorDevice {
  id: string
  type: string
  status: string
  battery?: number
  last_seen?: number
  [key: string]: unknown
}

export interface SimulatorStartRequest {
  org_id: string
  incident_id: string
  device_count?: number
  seed?: number
}

export interface SimulatorStartResponse {
  device_ids: string[]
  seed: number
  started_by: string
}

export interface CreateTaskRequest {
  title: string
  status?: string
  priority?: string
  required_capability?: string
  geometry?: GeoJSONGeometry | null
  properties?: Record<string, unknown>
}

export interface UpdateTaskStatusRequest {
  status: string
}

export interface ModifyAlertRequest {
  recommended_action: string
}
