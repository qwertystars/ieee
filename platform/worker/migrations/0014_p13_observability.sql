-- P13: Observability + Deployment + A11y + Localization

CREATE TABLE IF NOT EXISTS slo_metrics (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  p50 REAL,
  p95 REAL,
  p99 REAL,
  error_rate REAL,
  request_count INTEGER,
  period TEXT NOT NULL DEFAULT 'hourly',
  measured_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_slo_metrics_org ON slo_metrics(org_id);

CREATE TABLE IF NOT EXISTS cron_jobs (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  name TEXT NOT NULL,
  schedule TEXT NOT NULL,
  last_run_at INTEGER,
  last_status TEXT,
  next_run_at INTEGER,
  active INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_org ON cron_jobs(org_id);

CREATE TABLE IF NOT EXISTS locale_documents (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  locale TEXT NOT NULL,
  namespace TEXT NOT NULL,
  content TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_locale_documents_org ON locale_documents(org_id);
CREATE INDEX IF NOT EXISTS idx_locale_documents_locale ON locale_documents(locale);

CREATE TABLE IF NOT EXISTS glossary_terms (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  term TEXT NOT NULL,
  translations TEXT,
  locked INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_glossary_terms_org ON glossary_terms(org_id);
