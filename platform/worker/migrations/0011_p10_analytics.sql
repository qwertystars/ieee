-- P10: Analytics + Decision Support + Search/KB

CREATE TABLE IF NOT EXISTS analytics_rollups (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  metric_name TEXT NOT NULL,
  metric_value REAL NOT NULL,
  dimensions TEXT,
  period TEXT NOT NULL DEFAULT 'daily',
  rolled_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analytics_rollups_org ON analytics_rollups(org_id);
CREATE INDEX IF NOT EXISTS idx_analytics_rollups_metric ON analytics_rollups(metric_name);

CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  engine TEXT NOT NULL,
  title TEXT NOT NULL,
  recommendation TEXT,
  confidence REAL,
  citations TEXT,
  risk_score REAL,
  impact_estimate REAL,
  status TEXT NOT NULL DEFAULT 'draft',
  approved_by TEXT,
  approved_at INTEGER,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_org ON decisions(org_id);
CREATE INDEX IF NOT EXISTS idx_decisions_incident ON decisions(incident_id);

CREATE TABLE IF NOT EXISTS saved_searches (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  query TEXT NOT NULL,
  filters TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_searches_org ON saved_searches(org_id);

CREATE TABLE IF NOT EXISTS kb_documents (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  title TEXT NOT NULL,
  content_md TEXT NOT NULL,
  doc_type TEXT NOT NULL DEFAULT 'general',
  version INTEGER NOT NULL DEFAULT 1,
  tags TEXT,
  review_expiry_at INTEGER,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_documents_org ON kb_documents(org_id);
CREATE INDEX IF NOT EXISTS idx_kb_documents_type ON kb_documents(doc_type);
