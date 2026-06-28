import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

export const scenarios = sqliteTable('scenarios', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  modelType: text('model_type', {
    enum: ['fire_spread', 'flood', 'smoke', 'plume', 'dam_break', 'evac', 'shelter_demand', 'resource_demand', 'hospital_surge', 'seir', 'congestion', 'power_cascade', 'comms_cascade'],
  }).notNull(),
  params: text('params', { mode: 'json' }).$type<Record<string, unknown>>(),
  status: text('status', { enum: ['queued', 'running', 'completed', 'failed'] }).notNull().default('queued'),
  resultR2Key: text('result_r2_key'),
  resultGeoJson: text('result_geojson'),
  confidence: real('confidence'),
  scenarioLabel: text('scenario_label', { enum: ['best', 'expected', 'worst'] }),
  createdAt: nowMs(),
  completedAt: integer('completed_at'),
}, (t) => ({
  scenarioOrgIdx: index('idx_scenarios_org').on(t.orgId),
  scenarioIncidentIdx: index('idx_scenarios_incident').on(t.incidentId),
}));

export const droneMissions = sqliteTable('drone_missions', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  name: text('name').notNull(),
  surveyZone: text('survey_zone'),
  status: text('status', { enum: ['planned', 'in_flight', 'completed', 'aborted'] }).notNull().default('planned'),
  operatorId: text('operator_id'),
  batteryLevel: integer('battery_level'),
  liveLocation: text('live_location'),
  noFlyWarning: integer('no_fly_warning', { mode: 'boolean' }).notNull().default(false),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  droneMissionOrgIdx: index('idx_drone_missions_org').on(t.orgId),
  droneMissionIncidentIdx: index('idx_drone_missions_incident').on(t.incidentId),
}));

export const droneFlights = sqliteTable('drone_flights', {
  id: ulidPk(),
  orgId: orgId(),
  missionId: text('mission_id').notNull(),
  startTime: integer('start_time').notNull(),
  endTime: integer('end_time'),
  mediaR2Key: text('media_r2_key'),
  mediaType: text('media_type', { enum: ['image', 'thermal', 'video', 'orthomosaic'] }),
  cogR2Key: text('cog_r2_key'),
  altitudeM: real('altitude_m'),
  createdAt: nowMs(),
}, (t) => ({
  droneFlightOrgIdx: index('idx_drone_flights_org').on(t.orgId),
  droneFlightMissionIdx: index('idx_drone_flights_mission').on(t.missionId),
}));

export const damageReports = sqliteTable('damage_reports', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  assetClass: text('asset_class', {
    enum: ['building', 'road', 'bridge', 'utility', 'crop', 'industrial', 'shelter', 'hospital', 'school'],
  }).notNull(),
  severity: text('severity', { enum: ['affected', 'minor', 'major', 'destroyed'] }).notNull(),
  location: text('location'),
  photoR2Key: text('photo_r2_key'),
  exifLat: real('exif_lat'),
  exifLng: real('exif_lng'),
  exifVerified: integer('exif_verified', { mode: 'boolean' }).notNull().default(false),
  description: text('description'),
  estimatedLoss: real('estimated_loss'),
  repairPriority: integer('repair_priority'),
  verificationStatus: text('verification_status', { enum: ['pending', 'verified', 'rejected'] }).notNull().default('pending'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  damageReportOrgIdx: index('idx_damage_reports_org').on(t.orgId),
  damageReportIncidentIdx: index('idx_damage_reports_incident').on(t.incidentId),
  damageReportClassIdx: index('idx_damage_reports_class').on(t.assetClass),
}));
