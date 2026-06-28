-- P8: Evacuation + Medical + Logistics + Infrastructure

CREATE TABLE IF NOT EXISTS road_edges (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  region_id TEXT NOT NULL,
  from_node TEXT NOT NULL,
  to_node TEXT NOT NULL,
  length REAL NOT NULL,
  capacity INTEGER NOT NULL DEFAULT 100,
  oneway INTEGER NOT NULL DEFAULT 0,
  hazard_weight REAL NOT NULL DEFAULT 0,
  contraflow INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_road_edges_org ON road_edges(org_id);
CREATE INDEX IF NOT EXISTS idx_road_edges_region ON road_edges(region_id);
CREATE INDEX IF NOT EXISTS idx_road_edges_from ON road_edges(from_node);
CREATE INDEX IF NOT EXISTS idx_road_edges_to ON road_edges(to_node);

CREATE TABLE IF NOT EXISTS evac_zones (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  zone_name TEXT NOT NULL,
  geometry TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'advisory',
  priority INTEGER NOT NULL DEFAULT 1,
  estimated_pop INTEGER,
  route_r2_key TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evac_zones_org ON evac_zones(org_id);
CREATE INDEX IF NOT EXISTS idx_evac_zones_incident ON evac_zones(incident_id);

CREATE TABLE IF NOT EXISTS medical_facilities (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  geo TEXT,
  total_beds INTEGER NOT NULL DEFAULT 0,
  available_beds INTEGER NOT NULL DEFAULT 0,
  icu_beds INTEGER NOT NULL DEFAULT 0,
  er_beds INTEGER NOT NULL DEFAULT 0,
  ambulances INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open',
  fhir_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_medical_facilities_org ON medical_facilities(org_id);

CREATE TABLE IF NOT EXISTS triage_patients (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  facility_id TEXT,
  qr_wristband TEXT,
  triage_category TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'minor',
  name TEXT,
  age INTEGER,
  sex TEXT,
  transport_status TEXT NOT NULL DEFAULT 'pending',
  transport_request_id TEXT,
  mci_mode INTEGER NOT NULL DEFAULT 0,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_triage_patients_org ON triage_patients(org_id);
CREATE INDEX IF NOT EXISTS idx_triage_patients_incident ON triage_patients(incident_id);

CREATE TABLE IF NOT EXISTS logistics_items (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  unit TEXT NOT NULL DEFAULT 'each',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logistics_items_org ON logistics_items(org_id);

CREATE TABLE IF NOT EXISTS logistics_stock (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  location_id TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 0,
  lot TEXT,
  expiry INTEGER,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logistics_stock_org ON logistics_stock(org_id);
CREATE INDEX IF NOT EXISTS idx_logistics_stock_item ON logistics_stock(item_id);

CREATE TABLE IF NOT EXISTS logistics_movements (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  from_location TEXT,
  to_location TEXT,
  qty INTEGER NOT NULL,
  lot TEXT,
  movement_type TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  reference TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logistics_movements_org ON logistics_movements(org_id);
CREATE INDEX IF NOT EXISTS idx_logistics_movements_item ON logistics_movements(item_id);
CREATE INDEX IF NOT EXISTS idx_logistics_movements_idem ON logistics_movements(idempotency_key);

CREATE TABLE IF NOT EXISTS resource_requests (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  item_type TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  urgency TEXT NOT NULL DEFAULT 'medium',
  status TEXT NOT NULL DEFAULT 'requested',
  requested_by TEXT,
  approved_by TEXT,
  ics_213rr_ref TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resource_requests_org ON resource_requests(org_id);
CREATE INDEX IF NOT EXISTS idx_resource_requests_incident ON resource_requests(incident_id);
CREATE INDEX IF NOT EXISTS idx_resource_requests_status ON resource_requests(status);

CREATE TABLE IF NOT EXISTS infra_assets (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  geo TEXT,
  status TEXT NOT NULL DEFAULT 'unknown',
  restore_eta INTEGER,
  parent_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_infra_assets_org ON infra_assets(org_id);
CREATE INDEX IF NOT EXISTS idx_infra_assets_incident ON infra_assets(incident_id);
CREATE INDEX IF NOT EXISTS idx_infra_assets_type ON infra_assets(type);

CREATE TABLE IF NOT EXISTS infra_asset_deps (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  parent_id TEXT NOT NULL,
  child_id TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_infra_deps_parent ON infra_asset_deps(parent_id);
CREATE INDEX IF NOT EXISTS idx_infra_deps_child ON infra_asset_deps(child_id);
