-- P12: Multi-Agency + Drills + Early Warning + Recovery + Finance

CREATE TABLE IF NOT EXISTS agencies (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  name TEXT NOT NULL,
  capabilities TEXT,
  coverage_area TEXT,
  contact_name TEXT,
  contact_phone TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agencies_org ON agencies(org_id);

CREATE TABLE IF NOT EXISTS mous (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  agency_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  expiry INTEGER,
  doc_r2_key TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mous_org ON mous(org_id);

CREATE TABLE IF NOT EXISTS incident_shares (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  target_org_id TEXT NOT NULL,
  scope TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incident_shares_org ON incident_shares(org_id);
CREATE INDEX IF NOT EXISTS idx_incident_shares_incident ON incident_shares(incident_id);

CREATE TABLE IF NOT EXISTS exercises (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  name TEXT NOT NULL,
  exercise_mode TEXT NOT NULL DEFAULT 'tabletop',
  exercise_active INTEGER NOT NULL DEFAULT 0,
  injects_r2_key TEXT,
  start_time INTEGER,
  end_time INTEGER,
  status TEXT NOT NULL DEFAULT 'planned',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exercises_org ON exercises(org_id);

CREATE TABLE IF NOT EXISTS watches (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  hazard TEXT NOT NULL,
  geometry TEXT,
  state TEXT NOT NULL DEFAULT 'monitoring',
  threshold_rule TEXT,
  triggered_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_watches_org ON watches(org_id);

CREATE TABLE IF NOT EXISTS recovery_cases (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  household_ref TEXT,
  caseworker_id TEXT,
  stage TEXT NOT NULL DEFAULT 'intake',
  needs TEXT,
  cva_amount REAL,
  cva_status TEXT NOT NULL DEFAULT 'none',
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_org ON recovery_cases(org_id);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_incident ON recovery_cases(incident_id);

CREATE TABLE IF NOT EXISTS cost_codes (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  code TEXT NOT NULL,
  description TEXT,
  fema_category TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cost_codes_org ON cost_codes(org_id);

CREATE TABLE IF NOT EXISTS cost_entries (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  cost_code_id TEXT NOT NULL,
  amount INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  source TEXT NOT NULL,
  description TEXT,
  ics_214_ref TEXT,
  rate_card_id TEXT,
  hours REAL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cost_entries_org ON cost_entries(org_id);
CREATE INDEX IF NOT EXISTS idx_cost_entries_code ON cost_entries(cost_code_id);

CREATE TABLE IF NOT EXISTS rate_cards (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  role TEXT NOT NULL,
  hourly_rate INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  effective_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_cards_org ON rate_cards(org_id);
