import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

// ─── disaster_events (DESIGN.md §4: DisasterEvent) ──────────────────────────
// An active disaster event (flood, wildfire, etc.) scoped to an org + incident.

export const disasterEvents = sqliteTable(
  'disaster_events',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    name: text('name').notNull(),
    type: text('type').notNull(),
    status: text('status', {
      enum: ['monitoring', 'active', 'contained', 'resolved', 'closed'],
    }).notNull().default('active'),
    description: text('description'),
    affectedRegion: text('affected_region'),
    startsAt: integer('starts_at'),
    expectedEnd: integer('expected_end'),
    createdBy: text('created_by'),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (t) => ({
    disasterEventOrgIdx: index('idx_disaster_events_org').on(t.orgId),
    disasterEventIncidentIdx: index('idx_disaster_events_incident').on(t.incidentId),
    disasterEventStatusIdx: index('idx_disaster_events_status').on(t.status),
  }),
);

// ─── incident_reports (DESIGN.md §4: IncidentReport) ───────────────────────

export const incidentReports = sqliteTable(
  'incident_reports',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    reporterType: text('reporter_type', {
      enum: ['citizen', 'field_responder', 'sensor', 'official'],
    }).notNull(),
    reportCategory: text('report_category').notNull(),
    description: text('description'),
    geometry: text('geometry').notNull(),
    photoUrl: text('photo_url'),
    urgency: text('urgency', {
      enum: ['low', 'medium', 'high', 'critical'],
    }).notNull().default('medium'),
    verificationStatus: text('verification_status', {
      enum: ['unverified', 'low', 'medium', 'high'],
    }).notNull().default('unverified'),
    confidenceScore: real('confidence_score').notNull().default(0.5),
    piiRedactedText: text('pii_redacted_text'),
    clusterId: text('cluster_id'),
    visibility: visibility(),
    reviewStatus: reviewStatus(),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (t) => ({
    incidentReportOrgIdx: index('idx_incident_reports_org').on(t.orgId),
    incidentReportIncidentIdx: index('idx_incident_reports_incident').on(t.incidentId),
    incidentReportCategoryIdx: index('idx_incident_reports_category').on(t.reportCategory),
  }),
);

// ─── road_statuses (DESIGN.md §4: RoadStatus) ──────────────────────────────

export const roadStatuses = sqliteTable(
  'road_statuses',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    roadName: text('road_name').notNull(),
    geometry: text('geometry').notNull(),
    status: text('status', {
      enum: ['open', 'blocked', 'partially_blocked', 'unknown', 'dangerous'],
    }).notNull().default('unknown'),
    reason: text('reason'),
    confidenceScore: real('confidence_score').notNull().default(0.5),
    visibility: visibility(),
    reviewStatus: reviewStatus(),
    updatedAt: updatedAt(),
    createdAt: nowMs(),
  },
  (t) => ({
    roadStatusOrgIdx: index('idx_road_statuses_org').on(t.orgId),
    roadStatusIncidentIdx: index('idx_road_statuses_incident').on(t.incidentId),
    roadStatusStatusIdx: index('idx_road_statuses_status').on(t.status),
  }),
);

// ─── response_teams (DESIGN.md §4: ResponseTeam) ───────────────────────────

export const responseTeams = sqliteTable(
  'response_teams',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    name: text('name').notNull(),
    teamType: text('team_type').notNull(),
    currentLocation: text('current_location'),
    status: text('status', {
      enum: ['available', 'dispatched', 'on_scene', 'off_duty', 'standby'],
    }).notNull().default('available'),
    capacity: integer('capacity').notNull().default(4),
    assignedTaskId: text('assigned_task_id'),
    visibility: visibility(),
    reviewStatus: reviewStatus(),
    updatedAt: updatedAt(),
    createdAt: nowMs(),
  },
  (t) => ({
    responseTeamOrgIdx: index('idx_response_teams_org').on(t.orgId),
    responseTeamIncidentIdx: index('idx_response_teams_incident').on(t.incidentId),
    responseTeamStatusIdx: index('idx_response_teams_status').on(t.status),
  }),
);

// ─── tasks (DESIGN.md §4: Task) ────────────────────────────────────────────

export const tasks = sqliteTable(
  'tasks',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    recommendationId: text('recommendation_id'),
    assignedTeamId: text('assigned_team_id'),
    title: text('title').notNull(),
    description: text('description'),
    location: text('location'),
    priority: text('priority', {
      enum: ['low', 'medium', 'high', 'critical'],
    }).notNull().default('medium'),
    status: text('status', {
      enum: ['assigned', 'accepted', 'en_route', 'on_site', 'completed', 'blocked', 'cancelled'],
    }).notNull().default('assigned'),
    visibility: visibility(),
    reviewStatus: reviewStatus(),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (t) => ({
    taskOrgIdx: index('idx_tasks_org').on(t.orgId),
    taskIncidentIdx: index('idx_tasks_incident').on(t.incidentId),
    taskTeamIdx: index('idx_tasks_team').on(t.assignedTeamId),
    taskStatusIdx: index('idx_tasks_status').on(t.status),
  }),
);

// ─── shelters (DESIGN.md §4: Shelter) ─────────────────────────────────────

export const shelters = sqliteTable(
  'shelters',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    name: text('name').notNull(),
    geometry: text('geometry').notNull(),
    totalCapacity: integer('total_capacity').notNull().default(0),
    currentOccupancy: integer('current_occupancy').notNull().default(0),
    foodStatus: text('food_status', {
      enum: ['adequate', 'limited', 'critical', 'unknown'],
    }).notNull().default('unknown'),
    waterStatus: text('water_status', {
      enum: ['adequate', 'limited', 'critical', 'unknown'],
    }).notNull().default('unknown'),
    medicalSupport: integer('medical_support', { mode: 'boolean' }).notNull().default(false),
    accessibilitySupport: integer('accessibility_support', { mode: 'boolean' }).notNull().default(false),
    status: text('status', {
      enum: ['open', 'closed', 'full', 'preparing'],
    }).notNull().default('preparing'),
    visibility: visibility(),
    reviewStatus: reviewStatus(),
    updatedAt: updatedAt(),
    createdAt: nowMs(),
  },
  (t) => ({
    shelterOrgIdx: index('idx_shelters_org').on(t.orgId),
    shelterIncidentIdx: index('idx_shelters_incident').on(t.incidentId),
    shelterStatusIdx: index('idx_shelters_status').on(t.status),
  }),
);

// ─── recommendations (DESIGN.md §4: Recommendation) ────────────────────────

export const recommendations = sqliteTable(
  'recommendations',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    areaAssessmentId: text('area_assessment_id'),
    recommendationType: text('recommendation_type').notNull(),
    title: text('title').notNull(),
    description: text('description'),
    reasoning: text('reasoning'),
    supportingData: text('supporting_data', { mode: 'json' }).$type<Record<string, unknown>>(),
    confidenceScore: real('confidence_score').notNull().default(0.5),
    urgency: text('urgency', {
      enum: ['low', 'medium', 'high', 'critical'],
    }).notNull().default('medium'),
    status: text('status', {
      enum: ['draft', 'reviewed', 'approved', 'assigned', 'in_progress', 'completed', 'dismissed'],
    }).notNull().default('draft'),
    assignedTo: text('assigned_to'),
    visibility: visibility(),
    reviewStatus: reviewStatus(),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (t) => ({
    recommendationOrgIdx: index('idx_recommendations_org').on(t.orgId),
    recommendationIncidentIdx: index('idx_recommendations_incident').on(t.incidentId),
    recommendationStatusIdx: index('idx_recommendations_status').on(t.status),
  }),
);

// ─── alerts (DESIGN.md §4: Alert) ─────────────────────────────────────────

export const alerts = sqliteTable(
  'alerts',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    alertType: text('alert_type').notNull(),
    title: text('title').notNull(),
    message: text('message'),
    area: text('area'),
    severity: text('severity', {
      enum: ['info', 'advisory', 'warning', 'critical'],
    }).notNull().default('warning'),
    recommendedAction: text('recommended_action'),
    confidenceScore: real('confidence_score').notNull().default(0.5),
    acknowledged: integer('acknowledged', { mode: 'boolean' }).notNull().default(false),
    visibility: visibility(),
    reviewStatus: reviewStatus(),
    createdAt: nowMs(),
  },
  (t) => ({
    alertOrgIdx: index('idx_alerts_org').on(t.orgId),
    alertIncidentIdx: index('idx_alerts_incident').on(t.incidentId),
    alertSeverityIdx: index('idx_alerts_severity').on(t.severity),
  }),
);

// ─── area_assessments (DESIGN.md §4: AreaAssessment) ───────────────────────

export const areaAssessments = sqliteTable(
  'area_assessments',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    areaName: text('area_name').notNull(),
    geometry: text('geometry').notNull(),
    hazardScore: real('hazard_score').notNull().default(0),
    exposureScore: real('exposure_score').notNull().default(0),
    accessScore: real('access_score').notNull().default(0),
    infrastructureScore: real('infrastructure_score').notNull().default(0),
    vulnerabilityScore: real('vulnerability_score').notNull().default(0),
    trendScore: real('trend_score').notNull().default(0),
    reportScore: real('report_score').notNull().default(0),
    overallPriorityScore: real('overall_priority_score').notNull().default(0),
    priorityLevel: text('priority_level', {
      enum: ['critical', 'high', 'medium', 'low', 'monitoring', 'unknown'],
    }).notNull().default('unknown'),
    summary: text('summary'),
    components: text('components', { mode: 'json' }).$type<Record<string, unknown>>(),
    visibility: visibility(),
    reviewStatus: reviewStatus(),
    updatedAt: updatedAt(),
    createdAt: nowMs(),
  },
  (t) => ({
    areaAssessmentOrgIdx: index('idx_area_assessments_org').on(t.orgId),
    areaAssessmentIncidentIdx: index('idx_area_assessments_incident').on(t.incidentId),
    areaAssessmentPriorityIdx: index('idx_area_assessments_priority').on(t.priorityLevel),
  }),
);
