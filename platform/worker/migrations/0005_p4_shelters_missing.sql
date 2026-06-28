-- P4: Shelter Management + Missing Persons/Reunification

CREATE TABLE IF NOT EXISTS shelter_status (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  shelter_id TEXT NOT NULL,
  generator_fuel INTEGER,
  water_status TEXT NOT NULL DEFAULT 'unknown',
  food_status TEXT NOT NULL DEFAULT 'unknown',
  meal_capacity_day INTEGER,
  sanitation_ratio REAL,
  staff_count INTEGER NOT NULL DEFAULT 0,
  security_present INTEGER NOT NULL DEFAULT 0,
  pet_support INTEGER NOT NULL DEFAULT 0,
  accessibility_support INTEGER NOT NULL DEFAULT 0,
  medical_support INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shelter_status_org ON shelter_status(org_id);
CREATE INDEX IF NOT EXISTS idx_shelter_status_shelter ON shelter_status(shelter_id);

CREATE TABLE IF NOT EXISTS shelter_checkins (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  shelter_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  person_name TEXT NOT NULL,
  person_name_split TEXT,
  bed_number TEXT,
  family_group_id TEXT,
  vulnerable INTEGER NOT NULL DEFAULT 0,
  medical_needs INTEGER NOT NULL DEFAULT 0,
  dietary_needs TEXT,
  reunification_trigger_id TEXT,
  checked_in_at INTEGER NOT NULL,
  checked_out_at INTEGER,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft'
);
CREATE INDEX IF NOT EXISTS idx_shelter_checkins_org ON shelter_checkins(org_id);
CREATE INDEX IF NOT EXISTS idx_shelter_checkins_shelter ON shelter_checkins(shelter_id);
CREATE INDEX IF NOT EXISTS idx_shelter_checkins_family ON shelter_checkins(family_group_id);

CREATE TABLE IF NOT EXISTS shelter_supply_requests (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  shelter_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  item_type TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  urgency TEXT NOT NULL DEFAULT 'medium',
  status TEXT NOT NULL DEFAULT 'requested',
  ics_213rr_ref TEXT,
  notes TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shelter_supply_req_org ON shelter_supply_requests(org_id);
CREATE INDEX IF NOT EXISTS idx_shelter_supply_req_shelter ON shelter_supply_requests(shelter_id);
CREATE INDEX IF NOT EXISTS idx_shelter_supply_req_status ON shelter_supply_requests(status);

CREATE TABLE IF NOT EXISTS shelter_plans (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  shelter_id TEXT,
  plan_type TEXT NOT NULL,
  name TEXT NOT NULL,
  location TEXT,
  estimated_capacity INTEGER,
  hospital_id TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shelter_plans_org ON shelter_plans(org_id);
CREATE INDEX IF NOT EXISTS idx_shelter_plans_incident ON shelter_plans(incident_id);
CREATE INDEX IF NOT EXISTS idx_shelter_plans_type ON shelter_plans(plan_type);

CREATE TABLE IF NOT EXISTS missing_persons (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  full_name TEXT NOT NULL,
  full_name_split TEXT,
  age_group TEXT NOT NULL DEFAULT 'unknown',
  age_exact INTEGER,
  sex TEXT NOT NULL DEFAULT 'unknown',
  photo_r2_key TEXT,
  last_known_location TEXT,
  last_seen_at INTEGER,
  medical_condition TEXT,
  vulnerability TEXT NOT NULL DEFAULT 'none',
  description TEXT,
  contact_name TEXT,
  contact_phone TEXT,
  status TEXT NOT NULL DEFAULT 'missing',
  assigned_to TEXT,
  encrypted_fields TEXT,
  pfif_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_missing_persons_org ON missing_persons(org_id);
CREATE INDEX IF NOT EXISTS idx_missing_persons_incident ON missing_persons(incident_id);
CREATE INDEX IF NOT EXISTS idx_missing_persons_status ON missing_persons(status);
CREATE INDEX IF NOT EXISTS idx_missing_persons_pfif ON missing_persons(pfif_id);

CREATE TABLE IF NOT EXISTS found_persons (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  full_name TEXT NOT NULL,
  full_name_split TEXT,
  age_group TEXT NOT NULL DEFAULT 'unknown',
  sex TEXT NOT NULL DEFAULT 'unknown',
  photo_r2_key TEXT,
  found_location TEXT,
  found_at INTEGER,
  source TEXT NOT NULL DEFAULT 'shelter',
  source_ref TEXT,
  shelter_checkin_id TEXT,
  matched_missing_id TEXT,
  match_status TEXT NOT NULL DEFAULT 'pending',
  match_score REAL,
  encrypted_fields TEXT,
  pfif_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_found_persons_org ON found_persons(org_id);
CREATE INDEX IF NOT EXISTS idx_found_persons_incident ON found_persons(incident_id);
CREATE INDEX IF NOT EXISTS idx_found_persons_match ON found_persons(matched_missing_id);

CREATE TABLE IF NOT EXISTS missing_person_notes (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  missing_person_id TEXT NOT NULL,
  author_id TEXT NOT NULL,
  note TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_missing_notes_person ON missing_person_notes(missing_person_id);

CREATE TABLE IF NOT EXISTS reunification_cases (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  missing_person_id TEXT NOT NULL,
  found_person_id TEXT,
  status TEXT NOT NULL DEFAULT 'initiated',
  reunification_center_id TEXT,
  qr_card_r2_key TEXT,
  safe_and_well INTEGER NOT NULL DEFAULT 0,
  foreign_national INTEGER NOT NULL DEFAULT 0,
  embassy_notified INTEGER NOT NULL DEFAULT 0,
  is_deceased INTEGER NOT NULL DEFAULT 0,
  approved_by TEXT,
  approved_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reunification_org ON reunification_cases(org_id);
CREATE INDEX IF NOT EXISTS idx_reunification_missing ON reunification_cases(missing_person_id);
