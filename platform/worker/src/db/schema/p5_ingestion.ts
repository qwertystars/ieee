import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt } from './columns';
import { orgId } from './orgs';

// T75: Raw reports staging table
export const rawReports = sqliteTable('raw_reports', {
  id: ulidPk(),
  orgId: orgId(),
  source: text('source').notNull(),
  externalId: text('external_id').notNull(),
  payload: text('payload', { mode: 'json' }).$type<Record<string, unknown>>(),
  geo: text('geo'),
  observedAt: integer('observed_at'),
  confidence: real('confidence').notNull().default(0.5),
  status: text('status', {
    enum: ['staged', 'validated', 'promoted', 'quarantined', 'duplicate'],
  }).notNull().default('staged'),
  ingestLogId: text('ingest_log_id'),
  createdAt: nowMs(),
}, (t) => ({
  rawReportOrgIdx: index('idx_raw_reports_org').on(t.orgId),
  rawReportSourceIdx: index('idx_raw_reports_source').on(t.source, t.externalId),
  rawReportStatusIdx: index('idx_raw_reports_status').on(t.status),
}));

// T75: Ingest log (replayable)
export const ingestLogs = sqliteTable('ingest_logs', {
  id: ulidPk(),
  orgId: orgId(),
  source: text('source').notNull(),
  externalId: text('external_id'),
  action: text('action').notNull(),
  result: text('result'),
  createdAt: nowMs(),
}, (t) => ({
  ingestLogOrgIdx: index('idx_ingest_logs_org').on(t.orgId),
  ingestLogSourceIdx: index('idx_ingest_logs_source').on(t.source),
}));

// T77: Feed integrations registry
export const feedSources = sqliteTable('feed_sources', {
  id: ulidPk(),
  orgId: orgId(),
  name: text('name').notNull(),
  kind: text('kind', {
    enum: ['weather', 'seismic', 'river', 'fire', 'satellite', 'road', 'call', 'cap', 'rss'],
  }).notNull(),
  url: text('url'),
  config: text('config', { mode: 'json' }).$type<Record<string, unknown>>(),
  enabled: integer('enabled', { mode: 'boolean' }).notNull().default(true),
  lastSuccessAt: integer('last_success_at'),
  lastError: text('last_error'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  feedSourceOrgIdx: index('idx_feed_sources_org').on(t.orgId),
  feedSourceKindIdx: index('idx_feed_sources_kind').on(t.kind),
}));

// T83: Weather observations
export const weatherObs = sqliteTable('weather_obs', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  lat: real('lat'),
  lng: real('lng'),
  tempC: real('temp_c'),
  feelsLikeC: real('feels_like_c'),
  humidity: real('humidity'),
  windSpeedKmh: real('wind_speed_kmh'),
  windDirDeg: real('wind_dir_deg'),
  rainMm: real('rain_mm'),
  pressureHpa: real('pressure_hpa'),
  uvIndex: real('uv_index'),
  heatIndexC: real('heat_index_c'),
  airQuality: real('air_quality'),
  source: text('source').notNull().default('open-meteo'),
  observedAt: integer('observed_at').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  weatherObsOrgIdx: index('idx_weather_obs_org').on(t.orgId),
  weatherObsIncidentIdx: index('idx_weather_obs_incident').on(t.incidentId),
  weatherObsTimeIdx: index('idx_weather_obs_time').on(t.observedAt),
}));

// T83: Weather forecasts
export const weatherForecasts = sqliteTable('weather_forecasts', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  lat: real('lat'),
  lng: real('lng'),
  forecastAt: integer('forecast_at').notNull(),
  tempC: real('temp_c'),
  rainMm: real('rain_mm'),
  windSpeedKmh: real('wind_speed_kmh'),
  windDirDeg: real('wind_dir_deg'),
  humidity: real('humidity'),
  source: text('source').notNull().default('open-meteo'),
  createdAt: nowMs(),
}, (t) => ({
  weatherForecastOrgIdx: index('idx_weather_forecasts_org').on(t.orgId),
  weatherForecastIncidentIdx: index('idx_weather_forecasts_incident').on(t.incidentId),
}));

// T85: Population H3 grid
export const popH3 = sqliteTable('pop_h3', {
  h3: text('h3').primaryKey().notNull(),
  orgId: orgId(),
  pop: integer('pop').notNull().default(0),
  source: text('source').notNull().default('kontur'),
  createdAt: nowMs(),
}, (t) => ({
  popH3OrgIdx: index('idx_pop_h3_org').on(t.orgId),
}));

// T85: Population impact estimates
export const popEstimates = sqliteTable('pop_estimates', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  zoneId: text('zone_id'),
  totalAffected: integer('total_affected').notNull().default(0),
  elderly: integer('elderly').notNull().default(0),
  children: integer('children').notNull().default(0),
  disabled: integer('disabled').notNull().default(0),
  households: integer('households').notNull().default(0),
  buildings: integer('buildings').notNull().default(0),
  confidence: real('confidence').notNull().default(0.5),
  createdAt: nowMs(),
}, (t) => ({
  popEstimateOrgIdx: index('idx_pop_estimates_org').on(t.orgId),
  popEstimateIncidentIdx: index('idx_pop_estimates_incident').on(t.incidentId),
}));

// T87: Population needs estimates
export const popNeeds = sqliteTable('pop_needs', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  zoneId: text('zone_id'),
  evacNeeded: integer('evac_needed').notNull().default(0),
  shelterNeeded: integer('shelter_needed').notNull().default(0),
  medicalNeeded: integer('medical_needed').notNull().default(0),
  foodNeeded: integer('food_needed').notNull().default(0),
  waterLitersNeeded: integer('water_liters_needed').notNull().default(0),
  trapped: integer('trapped').notNull().default(0),
  unreachable: integer('unreachable').notNull().default(0),
  source: text('source').notNull().default('estimate'),
  createdAt: nowMs(),
}, (t) => ({
  popNeedsOrgIdx: index('idx_pop_needs_org').on(t.orgId),
  popNeedsIncidentIdx: index('idx_pop_needs_incident').on(t.incidentId),
}));

// T84: Weather risk indices
export const weatherIndices = sqliteTable('weather_indices', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  fwi: real('fwi'),
  floodRisk: real('flood_risk'),
  landslideRisk: real('landslide_risk'),
  heatwaveRisk: real('heatwave_risk'),
  smokeEstimate: real('smoke_estimate'),
  plumeEstimate: real('plume_estimate'),
  opRiskScore: real('op_risk_score'),
  createdAt: nowMs(),
}, (t) => ({
  weatherIndexOrgIdx: index('idx_weather_indices_org').on(t.orgId),
  weatherIndexIncidentIdx: index('idx_weather_indices_incident').on(t.incidentId),
}));
