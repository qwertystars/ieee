-- P13: Observability + Deployment + A11y + Localization
-- (migration already in 0014_p13_observability.sql)

-- P14: Sci-Fi Features

CREATE TABLE IF NOT EXISTS scifi_outputs (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  feature_type TEXT NOT NULL,
  output TEXT,
  confidence REAL,
  citations TEXT,
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scifi_outputs_org ON scifi_outputs(org_id);
CREATE INDEX IF NOT EXISTS idx_scifi_outputs_feature ON scifi_outputs(feature_type);
