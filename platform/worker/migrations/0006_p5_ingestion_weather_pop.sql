-- P5: Data Ingestion + Weather + Population Impact

CREATE TABLE IF NOT EXISTS raw_reports (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  payload TEXT,
  geo TEXT,
  observed_at INTEGER,
  confidence REAL NOT NULL DEFAULT 0.5,
  status TEXT NOT NULL DEFAULT 'staged',
  ingest_log_id TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_reports_org ON raw_reports(org_id);
CREATE INDEX IF NOT EXISTS idx_raw_reports_source ON raw_reports(source, external_id);
CREATE INDEX IF NOT EXISTS idx_raw_reports_status ON raw_reports(status);

CREATE TABLE IF NOT EXISTS ingest_logs (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  source TEXT NOT NULL,
  external_id TEXT,
  action TEXT NOT NULL,
  result TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ingest_logs_org ON ingest_logs(org_id);
CREATE INDEX IF NOT EXISTS idx_ingest_logs_source ON ingest_logs(source);

CREATE TABLE IF NOT EXISTS feed_sources (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  url TEXT,
  config TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_success_at INTEGER,
  last_error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feed_sources_org ON feed_sources(org_id);
CREATE INDEX IF NOT EXISTS idx_feed_sources_kind ON feed_sources(kind);

CREATE TABLE IF NOT EXISTS weather_obs (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  lat REAL,
  lng REAL,
  temp_c REAL,
  feels_like_c REAL,
  humidity REAL,
  wind_speed_kmh REAL,
  wind_dir_deg REAL,
  rain_mm REAL,
  pressure_hpa REAL,
  uv_index REAL,
  heat_index_c REAL,
  air_quality REAL,
  source TEXT NOT NULL DEFAULT 'open-meteo',
  observed_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weather_obs_org ON weather_obs(org_id);
CREATE INDEX IF NOT EXISTS idx_weather_obs_incident ON weather_obs(incident_id);
CREATE INDEX IF NOT EXISTS idx_weather_obs_time ON weather_obs(observed_at);

CREATE TABLE IF NOT EXISTS weather_forecasts (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  lat REAL,
  lng REAL,
  forecast_at INTEGER NOT NULL,
  temp_c REAL,
  rain_mm REAL,
  wind_speed_kmh REAL,
  wind_dir_deg REAL,
  humidity REAL,
  source TEXT NOT NULL DEFAULT 'open-meteo',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weather_forecasts_org ON weather_forecasts(org_id);
CREATE INDEX IF NOT EXISTS idx_weather_forecasts_incident ON weather_forecasts(incident_id);

CREATE TABLE IF NOT EXISTS pop_h3 (
  h3 TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  pop INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'kontur',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pop_h3_org ON pop_h3(org_id);

CREATE TABLE IF NOT EXISTS pop_estimates (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  zone_id TEXT,
  total_affected INTEGER NOT NULL DEFAULT 0,
  elderly INTEGER NOT NULL DEFAULT 0,
  children INTEGER NOT NULL DEFAULT 0,
  disabled INTEGER NOT NULL DEFAULT 0,
  households INTEGER NOT NULL DEFAULT 0,
  buildings INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0.5,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pop_estimates_org ON pop_estimates(org_id);
CREATE INDEX IF NOT EXISTS idx_pop_estimates_incident ON pop_estimates(incident_id);

CREATE TABLE IF NOT EXISTS pop_needs (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  zone_id TEXT,
  evac_needed INTEGER NOT NULL DEFAULT 0,
  shelter_needed INTEGER NOT NULL DEFAULT 0,
  medical_needed INTEGER NOT NULL DEFAULT 0,
  food_needed INTEGER NOT NULL DEFAULT 0,
  water_liters_needed INTEGER NOT NULL DEFAULT 0,
  trapped INTEGER NOT NULL DEFAULT 0,
  unreachable INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'estimate',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pop_needs_org ON pop_needs(org_id);
CREATE INDEX IF NOT EXISTS idx_pop_needs_incident ON pop_needs(incident_id);

CREATE TABLE IF NOT EXISTS weather_indices (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  fwi REAL,
  flood_risk REAL,
  landslide_risk REAL,
  heatwave_risk REAL,
  smoke_estimate REAL,
  plume_estimate REAL,
  op_risk_score REAL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weather_indices_org ON weather_indices(org_id);
CREATE INDEX IF NOT EXISTS idx_weather_indices_incident ON weather_indices(incident_id);
