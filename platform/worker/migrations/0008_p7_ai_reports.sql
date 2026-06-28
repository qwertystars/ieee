-- P7: AI Configuration + Reports

CREATE TABLE IF NOT EXISTS ai_calls (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  prompt_name TEXT NOT NULL,
  prompt_version INTEGER NOT NULL DEFAULT 1,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  latency_ms INTEGER,
  cost REAL,
  success INTEGER NOT NULL DEFAULT 1,
  error TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_calls_org ON ai_calls(org_id);
CREATE INDEX IF NOT EXISTS idx_ai_calls_prompt ON ai_calls(prompt_name);

CREATE TABLE IF NOT EXISTS prompts (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  name TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  body TEXT NOT NULL,
  schema TEXT,
  temperature REAL DEFAULT 0.7,
  active INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prompts_org ON prompts(org_id);
CREATE INDEX IF NOT EXISTS idx_prompts_name ON prompts(name);

CREATE TABLE IF NOT EXISTS ai_outputs (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  prompt_name TEXT NOT NULL,
  output TEXT,
  confidence REAL,
  citations TEXT,
  hallucination_flag INTEGER NOT NULL DEFAULT 0,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  approved_by TEXT,
  approved_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_outputs_org ON ai_outputs(org_id);
CREATE INDEX IF NOT EXISTS idx_ai_outputs_incident ON ai_outputs(incident_id);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  title TEXT NOT NULL,
  report_type TEXT NOT NULL,
  template_id TEXT,
  content_md TEXT,
  content_html TEXT,
  r2_key TEXT,
  share_token TEXT,
  share_expiry INTEGER,
  scheduled_at INTEGER,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  version INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_org ON reports(org_id);
CREATE INDEX IF NOT EXISTS idx_reports_incident ON reports(incident_id);
CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type);

CREATE TABLE IF NOT EXISTS report_templates (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  name TEXT NOT NULL,
  report_type TEXT NOT NULL,
  template_md TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_report_templates_org ON report_templates(org_id);
