import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt } from './columns';
import { orgId } from './orgs';

export const securityLogs = sqliteTable('security_logs', {
  id: ulidPk(),
  orgId: orgId(),
  action: text('action').notNull(),
  actor: text('actor'),
  entityType: text('entity_type'),
  entityId: text('entity_id'),
  ipAddr: text('ip_addr'),
  userAgent: text('user_agent'),
  details: text('details', { mode: 'json' }).$type<Record<string, unknown>>(),
  createdAt: nowMs(),
}, (t) => ({
  securityLogOrgIdx: index('idx_security_logs_org').on(t.orgId),
}));

export const retentionPolicies = sqliteTable('retention_policies', {
  id: ulidPk(),
  orgId: orgId(),
  dataClass: text('data_class').notNull(),
  ttlDays: integer('ttl_days').notNull(),
  legalHold: integer('legal_hold', { mode: 'boolean' }).notNull().default(false),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  retentionOrgIdx: index('idx_retention_policies_org').on(t.orgId),
}));

export const consents = sqliteTable('consents', {
  id: ulidPk(),
  orgId: orgId(),
  personRef: text('person_ref').notNull(),
  purpose: text('purpose').notNull(),
  granted: integer('granted', { mode: 'boolean' }).notNull().default(true),
  grantedAt: integer('granted_at'),
  revokedAt: integer('revoked_at'),
  createdAt: nowMs(),
}, (t) => ({
  consentOrgIdx: index('idx_consents_org').on(t.orgId),
  consentPersonIdx: index('idx_consents_person').on(t.personRef),
}));

export const featureFlags = sqliteTable('feature_flags', {
  id: ulidPk(),
  orgId: orgId(),
  key: text('key').notNull(),
  enabled: integer('enabled', { mode: 'boolean' }).notNull().default(false),
  scope: text('scope', { enum: ['global', 'org', 'incident'] }).notNull().default('global'),
  incidentId: text('incident_id'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  flagOrgIdx: index('idx_feature_flags_org').on(t.orgId),
  flagKeyIdx: index('idx_feature_flags_key').on(t.key),
}));

export const announcements = sqliteTable('announcements', {
  id: ulidPk(),
  orgId: orgId(),
  message: text('message').notNull(),
  level: text('level', { enum: ['info', 'warning', 'critical'] }).notNull().default('info'),
  active: integer('active', { mode: 'boolean' }).notNull().default(true),
  dismissible: integer('dismissible', { mode: 'boolean' }).notNull().default(true),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  announcementOrgIdx: index('idx_announcements_org').on(t.orgId),
}));

export const limitCounters = sqliteTable('limit_counters', {
  id: ulidPk(),
  orgId: orgId(),
  scope: text('scope').notNull(),
  count: integer('count').notNull().default(0),
  windowStart: integer('window_start').notNull(),
}, (t) => ({
  limitCounterOrgIdx: index('idx_limit_counters_org').on(t.orgId),
}));

export const dsrRequests = sqliteTable('dsr_requests', {
  id: ulidPk(),
  orgId: orgId(),
  personRef: text('person_ref').notNull(),
  requestType: text('request_type', { enum: ['export', 'delete', 'rectify'] }).notNull(),
  status: text('status', { enum: ['pending', 'processing', 'completed', 'rejected'] }).notNull().default('pending'),
  resultR2Key: text('result_r2_key'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  dsrOrgIdx: index('idx_dsr_requests_org').on(t.orgId),
}));

export const complianceRecords = sqliteTable('compliance_records', {
  id: ulidPk(),
  orgId: orgId(),
  recordType: text('record_type').notNull(),
  data: text('data', { mode: 'json' }).$type<Record<string, unknown>>(),
  createdAt: nowMs(),
}, (t) => ({
  complianceOrgIdx: index('idx_compliance_records_org').on(t.orgId),
}));
