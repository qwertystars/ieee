-- P9: Prediction/Simulation + Drone + Damage Assessment

CREATE TABLE IF NOT EXISTS scenarios (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  model_type TEXT NOT NULL,
  params TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  result_r2_key TEXT,
  result_geojson TEXT,
  confidence REAL,
  scenario_label TEXT,
  created_at INTEGER NOT NULL,
  completed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_scenarios_org ON scenarios(org_id);
CREATE INDEX IF NOT EXISTS idx_scenarios_incident ON scenarios(incident_id);

CREATE TABLE IF NOT EXISTS drone_missions (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  name TEXT NOT NULL,
  survey_zone TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  operator_id TEXT,
  battery_level INTEGER,
  live_location TEXT,
  no_fly_warning INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drone_missions_org ON drone_missions(org_id);
CREATE INDEX IF NOT EXISTS idx_drone_missions_incident ON drone_missions(incident_id);

CREATE TABLE IF NOT EXISTS drone_flights (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  mission_id TEXT NOT NULL,
  start_time INTEGER NOT NULL,
  end_time INTEGER,
  media_r2_key TEXT,
  media_type TEXT,
  cog_r2_key TEXT,
  altitude_m REAL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drone_flights_org ON drone_flights(org_id);
CREATE INDEX IF NOT EXISTS idx_drone_flights_mission ON drone_flights(mission_id);

CREATE TABLE IF NOT EXISTS damage_reports (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  asset_class TEXT NOT NULL,
  severity TEXT NOT NULL,
  location TEXT,
  photo_r2_key TEXT,
  exif_lat REAL,
  exif_lng REAL,
  exif_verified INTEGER NOT NULL DEFAULT 0,
  description TEXT,
  estimated_loss REAL,
  repair_priority INTEGER,
  verification_status TEXT NOT NULL DEFAULT 'pending',
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_damage_reports_org ON damage_reports(org_id);
CREATE INDEX IF NOT EXISTS idx_damage_reports_incident ON damage_reports(incident_id);
CREATE INDEX IF NOT EXISTS idx_damage_reports_class ON damage_reports(asset_class);
