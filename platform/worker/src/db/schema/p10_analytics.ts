import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

export const analyticsRollups = sqliteTable('analytics_rollups', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  metricName: text('metric_name').notNull(),
  metricValue: real('metric_value').notNull(),
  dimensions: text('dimensions', { mode: 'json' }).$type<Record<string, unknown>>(),
  period: text('period', { enum: ['hourly', 'daily', 'weekly'] }).notNull().default('daily'),
  rolledAt: integer('rolled_at').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  analyticsRollupOrgIdx: index('idx_analytics_rollups_org').on(t.orgId),
  analyticsRollupMetricIdx: index('idx_analytics_rollups_metric').on(t.metricName),
}));

export const decisions = sqliteTable('decisions', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  engine: text('engine').notNull(),
  title: text('title').notNull(),
  recommendation: text('recommendation'),
  confidence: real('confidence'),
  citations: text('citations', { mode: 'json' }).$type<string[]>(),
  riskScore: real('risk_score'),
  impactEstimate: real('impact_estimate'),
  status: text('status', { enum: ['draft', 'approved', 'rejected', 'implemented'] }).notNull().default('draft'),
  approvedBy: text('approved_by'),
  approvedAt: integer('approved_at'),
  prevHash: text('prev_hash').notNull(),
  hash: text('hash').notNull(),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  decisionOrgIdx: index('idx_decisions_org').on(t.orgId),
  decisionIncidentIdx: index('idx_decisions_incident').on(t.incidentId),
}));

export const savedSearches = sqliteTable('saved_searches', {
  id: ulidPk(),
  orgId: orgId(),
  userId: text('user_id').notNull(),
  name: text('name').notNull(),
  query: text('query').notNull(),
  filters: text('filters', { mode: 'json' }).$type<Record<string, unknown>>(),
  createdAt: nowMs(),
}, (t) => ({
  savedSearchOrgIdx: index('idx_saved_searches_org').on(t.orgId),
}));

export const kbDocuments = sqliteTable('kb_documents', {
  id: ulidPk(),
  orgId: orgId(),
  title: text('title').notNull(),
  contentMd: text('content_md').notNull(),
  docType: text('doc_type', { enum: ['sop', 'playbook', 'law', 'contact', 'guide', 'general'] }).notNull().default('general'),
  version: integer('version').notNull().default(1),
  tags: text('tags', { mode: 'json' }).$type<string[]>(),
  reviewExpiryAt: integer('review_expiry_at'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  kbDocOrgIdx: index('idx_kb_documents_org').on(t.orgId),
  kbDocTypeIdx: index('idx_kb_documents_type').on(t.docType),
}));
