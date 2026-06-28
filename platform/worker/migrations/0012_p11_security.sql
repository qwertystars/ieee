-- P11: Security + Compliance + Admin + Developer Platform + Offline

CREATE TABLE IF NOT EXISTS security_logs (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  action TEXT NOT NULL,
  actor TEXT,
  entity_type TEXT,
  entity_id TEXT,
  ip_addr TEXT,
  user_agent TEXT,
  details TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_logs_org ON security_logs(org_id);

CREATE TABLE IF NOT EXISTS retention_policies (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  data_class TEXT NOT NULL,
  ttl_days INTEGER NOT NULL,
  legal_hold INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retention_policies_org ON retention_policies(org_id);

CREATE TABLE IF NOT EXISTS consents (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  person_ref TEXT NOT NULL,
  purpose TEXT NOT NULL,
  granted INTEGER NOT NULL DEFAULT 1,
  granted_at INTEGER,
  revoked_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consents_org ON consents(org_id);
CREATE INDEX IF NOT EXISTS idx_consents_person ON consents(person_ref);

CREATE TABLE IF NOT EXISTS feature_flags (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  key TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  scope TEXT NOT NULL DEFAULT 'global',
  incident_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feature_flags_org ON feature_flags(org_id);
CREATE INDEX IF NOT EXISTS idx_feature_flags_key ON feature_flags(key);

CREATE TABLE IF NOT EXISTS announcements (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  message TEXT NOT NULL,
  level TEXT NOT NULL DEFAULT 'info',
  active INTEGER NOT NULL DEFAULT 1,
  dismissible INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_announcements_org ON announcements(org_id);

CREATE TABLE IF NOT EXISTS limit_counters (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  window_start INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_limit_counters_org ON limit_counters(org_id);

CREATE TABLE IF NOT EXISTS dsr_requests (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  person_ref TEXT NOT NULL,
  request_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  result_r2_key TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dsr_requests_org ON dsr_requests(org_id);

CREATE TABLE IF NOT EXISTS compliance_records (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  record_type TEXT NOT NULL,
  data TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_compliance_records_org ON compliance_records(org_id);
