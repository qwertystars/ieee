// TypeScript mirror of backend Pydantic schemas (DESIGN §4, §5, §8)
// Keep in sync with app/schemas/

// ── Enums ──────────────────────────────────────────────────────────────────

export type UserRole =
  | 'admin'
  | 'emergency_manager'
  | 'responder_coordinator'
  | 'field_responder'
  | 'shelter_manager'
  | 'viewer'

export type DisasterType = 'flood' | 'earthquake' | 'fire' | 'hurricane' | 'landslide' | 'other'

export type EventStatus = 'active' | 'monitoring' | 'resolved' | 'archived'

export type DataSourceType = 'weather_api' | 'river_gauge' | 'satellite' | 'citizen_report' | 'government_feed' | 'sensor' | 'other'

export type ObservationType =
  | 'water_level'
  | 'flood_extent'
  | 'road_closure'
  | 'power_outage'
  | 'structural_damage'
  | 'weather'
  | 'crowd_report'
  | 'other'

export type ReporterType = 'citizen' | 'field_responder' | 'automated_sensor' | 'official'

export type ReportCategory =
  | 'trapped_person'
  | 'road_blocked'
  | 'flooding'
  | 'power_outage'
  | 'shelter_need'
  | 'medical_emergency'
  | 'infrastructure_damage'
  | 'other'

export type Urgency = 'low' | 'medium' | 'high' | 'critical'

export type VerificationStatus = 'unverified' | 'low' | 'medium' | 'high'

export type PriorityLevel = 'critical' | 'high' | 'medium' | 'low' | 'monitoring' | 'unknown'

export type RecommendationType =
  | 'evacuation'
  | 'rescue_operation'
  | 'shelter_activation'
  | 'road_closure'
  | 'resource_deployment'
  | 'medical_response'
  | 'utility_shutdown'
  | 'other'

export type RecommendationStatus =
  | 'draft'
  | 'reviewed'
  | 'approved'
  | 'assigned'
  | 'in_progress'
  | 'completed'
  | 'dismissed'

export type RoadStatusEnum = 'open' | 'blocked' | 'partially_blocked' | 'unknown' | 'dangerous'

export type TeamType = 'rescue' | 'medical' | 'logistics' | 'engineering' | 'coordination'

export type TaskStatus =
  | 'assigned'
  | 'accepted'
  | 'en_route'
  | 'on_site'
  | 'completed'
  | 'blocked'
  | 'cancelled'

export type ShelterStatus = 'open' | 'full' | 'closed' | 'evacuated'

export type ProcessingStatus = 'pending' | 'processed' | 'error'

// ── GeoJSON geometry ────────────────────────────────────────────────────────

export interface GeoPoint {
  type: 'Point'
  coordinates: [number, number] // [lng, lat]
}

export interface GeoLineString {
  type: 'LineString'
  coordinates: [number, number][]
}

export interface GeoPolygon {
  type: 'Polygon'
  coordinates: [number, number][][]
}

export interface GeoMultiPolygon {
  type: 'MultiPolygon'
  coordinates: [number, number][][][]
}

export type GeoGeometry = GeoPoint | GeoLineString | GeoPolygon | GeoMultiPolygon

// ── Auth ────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
}

export interface UserRead {
  id: string
  name: string
  email: string
  role: UserRole
  organization: string | null
  phone: string | null
  status: string
  created_at: string
  updated_at: string
}

// ── Events ──────────────────────────────────────────────────────────────────

export interface DisasterEventRead {
  id: string
  name: string
  type: DisasterType
  status: EventStatus
  start_time: string
  end_time: string | null
  description: string | null
  affected_region: GeoPolygon | GeoMultiPolygon | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface DisasterEventCreate {
  name: string
  type: DisasterType
  status?: EventStatus
  start_time: string
  end_time?: string
  description?: string
  affected_region?: GeoPolygon | GeoMultiPolygon
}

// ── Data Sources ────────────────────────────────────────────────────────────

export interface DataSourceRead {
  id: string
  name: string
  type: DataSourceType
  provider: string
  refresh_interval_s: number
  last_success_at: string | null
  last_error: string | null
  status: string
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

// ── Observations ────────────────────────────────────────────────────────────

export interface NormalizedObservationRead {
  id: string
  event_id: string
  source_id: string
  observation_type: ObservationType
  geometry: GeoGeometry
  timestamp: string
  value: number | null
  unit: string | null
  description: string | null
  confidence_score: number
  metadata: Record<string, unknown>
  cluster_id: string | null
  created_at: string
}

// ── Incident Reports ────────────────────────────────────────────────────────

export interface IncidentReportRead {
  id: string
  event_id: string
  reporter_type: ReporterType
  report_category: ReportCategory
  description: string
  geometry: GeoPoint
  photo_url: string | null
  urgency: Urgency
  verification_status: VerificationStatus
  confidence_score: number
  pii_redacted_text: string | null
  cluster_id: string | null
  created_at: string
  updated_at: string
}

export interface IncidentReportCreate {
  event_id: string
  reporter_type: ReporterType
  report_category: ReportCategory
  description: string
  geometry: GeoPoint
  photo_url?: string
  urgency: Urgency
  metadata?: Record<string, unknown>
}

// ── Area Assessments ────────────────────────────────────────────────────────

export interface AreaAssessmentRead {
  id: string
  event_id: string
  area_name: string
  geometry: GeoPolygon
  hazard_score: number
  exposure_score: number
  access_score: number
  infrastructure_score: number
  vulnerability_score: number
  trend_score: number
  report_score: number
  overall_priority_score: number
  priority_level: PriorityLevel
  summary: string | null
  components: Record<string, unknown>
  updated_at: string
}

// ── Recommendations ─────────────────────────────────────────────────────────

export interface RecommendationRead {
  id: string
  event_id: string
  area_assessment_id: string | null
  recommendation_type: RecommendationType
  title: string
  description: string
  reasoning: string
  supporting_data: Record<string, unknown>
  confidence_score: number
  urgency: Urgency
  status: RecommendationStatus
  assigned_to: string | null
  created_at: string
  updated_at: string
}

// ── Tasks ───────────────────────────────────────────────────────────────────

export interface TaskRead {
  id: string
  event_id: string
  recommendation_id: string | null
  assigned_team_id: string | null
  title: string
  description: string
  location: GeoPoint
  priority: Urgency
  status: TaskStatus
  created_at: string
  updated_at: string
}

export interface TaskCreate {
  event_id: string
  recommendation_id?: string
  assigned_team_id?: string
  title: string
  description: string
  location: GeoPoint
  priority: Urgency
}

export interface TaskUpdate {
  status?: TaskStatus
  assigned_team_id?: string
  description?: string
}

// ── Shelters ────────────────────────────────────────────────────────────────

export interface ShelterRead {
  id: string
  name: string
  geometry: GeoPoint
  total_capacity: number
  current_occupancy: number
  available_capacity: number
  food_status: string
  water_status: string
  medical_support: boolean
  accessibility_support: boolean
  status: ShelterStatus
  updated_at: string
}

// ── Roads ───────────────────────────────────────────────────────────────────

export interface RoadStatusRead {
  id: string
  event_id: string
  road_name: string
  geometry: GeoLineString
  status: RoadStatusEnum
  reason: string | null
  confidence_score: number
  updated_at: string
}

// ── Response Teams ──────────────────────────────────────────────────────────

export interface ResponseTeamRead {
  id: string
  name: string
  team_type: TeamType
  current_location: GeoPoint
  status: string
  capacity: number
  assigned_task_id: string | null
  updated_at: string
}

// ── Dashboard ───────────────────────────────────────────────────────────────

export interface DashboardSummary {
  event_id: string
  total_observations: number
  total_reports: number
  unverified_reports: number
  critical_areas: number
  high_areas: number
  medium_areas: number
  low_areas: number
  active_recommendations: number
  pending_tasks: number
  shelters_open: number
  shelters_full: number
  roads_blocked: number
  teams_deployed: number
  alerts_active: number
  last_updated: string
}

export interface MapLayersResponse {
  event_id: string
  observations: NormalizedObservationRead[]
  reports: IncidentReportRead[]
  areas: AreaAssessmentRead[]
  shelters: ShelterRead[]
  roads: RoadStatusRead[]
  teams: ResponseTeamRead[]
}

// ── Alerts ──────────────────────────────────────────────────────────────────

export interface AlertRead {
  id: string
  event_id: string
  alert_type: string
  title: string
  message: string
  area: GeoGeometry | null
  severity: Urgency
  recommended_action: string | null
  confidence_score: number
  acknowledged: boolean
  created_at: string
}

// ── Audit ───────────────────────────────────────────────────────────────────

export interface AuditLogRead {
  id: string
  user_id: string | null
  action: string
  target_type: string
  target_id: string | null
  details: Record<string, unknown>
  created_at: string
}

// ── Situation Report ────────────────────────────────────────────────────────

export interface SituationReportRequest {
  format: 'text' | 'pdf'
}

// ── Pagination ──────────────────────────────────────────────────────────────

export interface PaginatedParams {
  limit?: number
  offset?: number
  bbox?: string // "minx,miny,maxx,maxy"
}

// ── WebSocket events ────────────────────────────────────────────────────────

export type WsEventType =
  | 'new_observation'
  | 'new_report'
  | 'report_verified'
  | 'area_priority_changed'
  | 'recommendation_created'
  | 'recommendation_approved'
  | 'task_assigned'
  | 'task_status_changed'
  | 'shelter_status_changed'
  | 'road_status_changed'
  | 'team_location_updated'
  | 'alert_created'

export interface WsEvent<T = unknown> {
  type: WsEventType
  event_id: string
  payload: T
  timestamp: string
}
