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
  title: string
  disaster_type: string
  severity: string
  status: string
  declaration_level?: string | null
  description?: string | null
  start_time: number
  expected_end?: number | null
  config?: Record<string, unknown> | null
  geometry?: GeoJSONGeometry | null
  created_at: number
  updated_at: number
}

export interface IncidentList {
  incidents: Incident[]
  count: number
}

export interface Observation {
  observation_id: string
  event_type: string
  phenomenon: string
  value?: number | null
  unit?: string | null
  geometry_uncertainty: number
  observed_at: number
  valid_from: number
  valid_until?: number | null
  received_at: number
  source_id: string
  source_type?: string | null
  collection_method: string
  source_reliability: number
  freshness: number
  corroboration_state?: string | null
  model_uncertainty?: number | null
  quality_flags?: Record<string, unknown> | null
  access_policy?: string | null
  provenance_chain?: Record<string, unknown> | null
  raw_data_hash?: string
  model_version?: string | null
  supersedes?: string | null
  duplicate_group?: string | null
  org_id: string
  incident_id: string
}

export interface ObservationCollection {
  type: 'FeatureCollection'
  features: GeoJSONFeature<Observation>[]
}

export interface ConfidenceVector {
  s?: number
  c?: number
  f?: number
  [key: string]: unknown
}

export interface Hypothesis {
  id: string
  org_id: string
  incident_id: string
  entity_type: string
  entity_id: string
  claim: string
  probability: number
  supporting_evidence: Record<string, unknown> | null
  contradicting_evidence: Record<string, unknown> | null
  status: string
  created_at: number
  updated_at: number
  data_age_ms: number
}

export interface HypothesisList {
  hypotheses: Hypothesis[]
  count: number
}

export interface Alert {
  id: string
  org_id: string
  incident_id: string
  alert_type: string
  title: string
  message: string
  severity: string
  recommended_action?: string | null
  confidence_vector?: ConfidenceVector | null
  status: string
  created_by: string
  created_at: number
  updated_at: number
  reviewed_by?: string | null
  review_rationale?: string | null
  reviewed_at?: number | null
}

export interface AlertList {
  alerts: Alert[]
  count: number
}

export interface Task {
  id: string
  org_id: string
  incident_id: string
  title: string
  status: string
  priority?: string | null
  assigned_team_id?: string | null
  required_capability?: string | null
  assignment_history?: unknown
  properties?: Record<string, unknown> | null
  geometry?: GeoJSONGeometry | null
  created_at: number
  updated_at: number
}

export interface TaskList {
  tasks: Task[]
  count: number
}

export interface SituationReport {
  incident_id?: string
  generated_at: number
  window_ms?: number
  incident?: Record<string, unknown>
  observations?: Record<string, unknown>[]
  hazards?: Record<string, unknown>[]
  hypotheses?: Record<string, unknown>[]
  roads?: Record<string, unknown>[]
  shelters?: Record<string, unknown>[]
  tasks?: Record<string, unknown>[]
  alerts?: Record<string, unknown>[]
  responders?: Record<string, unknown>[]
  provenance_links?: Record<string, unknown>[]
  narrative?: Record<string, unknown> | null
  narrative_error?: string | null
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
  state: 'stopped' | 'running' | 'paused'
  device_count: number
  speed: number
  seed: number
  sim_time_ms: number
  device_ids: string[]
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

export interface InjectFaultRequest {
  device_id: string
  fault_type: string
  kwargs?: Record<string, unknown>
}

export interface InjectFaultResponse {
  device_id: string
  fault_type: string
  injected_by: string
}

export interface AuditVerifyResponse {
  valid: boolean
  first_broken_index?: number
}

export interface ProvenanceEntry {
  id: string
  ts: number
  prev_hash: string
  hash: string
  [key: string]: unknown
}

export interface ProvenanceResponse {
  recommendation_id: string
  entries: ProvenanceEntry[]
  verified: boolean
}

export interface UpdateEntityRequest {
  status?: string
  name?: string
  severity?: string
  priority?: string
  capacity?: number
  occupancy?: number
  properties?: Record<string, unknown>
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
