-- P6: Communications + Public Portal

CREATE TABLE IF NOT EXISTS alert_deliveries (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  alert_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  recipient TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  provider_message_id TEXT,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  delivered_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_org ON alert_deliveries(org_id);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_alert ON alert_deliveries(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_status ON alert_deliveries(status);

CREATE TABLE IF NOT EXISTS alert_templates (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  name TEXT NOT NULL,
  channel TEXT NOT NULL,
  subject_template TEXT,
  body_template TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT 'en',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_templates_org ON alert_templates(org_id);

CREATE TABLE IF NOT EXISTS comms_drafts (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  draft_type TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  channel TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  visibility TEXT NOT NULL DEFAULT 'internal',
  review_status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comms_drafts_org ON comms_drafts(org_id);
CREATE INDEX IF NOT EXISTS idx_comms_drafts_incident ON comms_drafts(incident_id);
CREATE INDEX IF NOT EXISTS idx_comms_drafts_type ON comms_drafts(draft_type);

CREATE TABLE IF NOT EXISTS public_subscriptions (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  incident_id TEXT,
  phone TEXT,
  email TEXT,
  geo_polygon TEXT,
  channels TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  active INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_public_subs_org ON public_subscriptions(org_id);
CREATE INDEX IF NOT EXISTS idx_public_subs_incident ON public_subscriptions(incident_id);

CREATE TABLE IF NOT EXISTS webhook_subscriptions (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  url TEXT NOT NULL,
  events TEXT NOT NULL,
  secret TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhook_subs_org ON webhook_subscriptions(org_id);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id TEXT PRIMARY KEY NOT NULL,
  org_id TEXT NOT NULL,
  subscription_id TEXT NOT NULL,
  event TEXT NOT NULL,
  payload TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  response_code INTEGER,
  error TEXT,
  delivered_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_org ON webhook_deliveries(org_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_sub ON webhook_deliveries(subscription_id);
