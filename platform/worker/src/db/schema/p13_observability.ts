import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt } from './columns';
import { orgId } from './orgs';

export const sloMetrics = sqliteTable('slo_metrics', {
  id: ulidPk(),
  orgId: orgId(),
  metricName: text('metric_name').notNull(),
  p50: real('p50'),
  p95: real('p95'),
  p99: real('p99'),
  errorRate: real('error_rate'),
  requestCount: integer('request_count'),
  period: text('period').notNull().default('hourly'),
  measuredAt: integer('measured_at').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  sloMetricOrgIdx: index('idx_slo_metrics_org').on(t.orgId),
}));

export const cronJobs = sqliteTable('cron_jobs', {
  id: ulidPk(),
  orgId: orgId(),
  name: text('name').notNull(),
  schedule: text('schedule').notNull(),
  lastRunAt: integer('last_run_at'),
  lastStatus: text('last_status'),
  nextRunAt: integer('next_run_at'),
  active: integer('active', { mode: 'boolean' }).notNull().default(true),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  cronJobOrgIdx: index('idx_cron_jobs_org').on(t.orgId),
}));

export const localeDocuments = sqliteTable('locale_documents', {
  id: ulidPk(),
  orgId: orgId(),
  locale: text('locale').notNull(),
  namespace: text('namespace').notNull(),
  content: text('content', { mode: 'json' }).$type<Record<string, unknown>>(),
  version: integer('version').notNull().default(1),
  reviewStatus: text('review_status', { enum: ['draft', 'reviewed', 'approved'] }).notNull().default('draft'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  localeDocOrgIdx: index('idx_locale_documents_org').on(t.orgId),
  localeDocLocaleIdx: index('idx_locale_documents_locale').on(t.locale),
}));

export const glossaryTerms = sqliteTable('glossary_terms', {
  id: ulidPk(),
  orgId: orgId(),
  term: text('term').notNull(),
  translations: text('translations', { mode: 'json' }).$type<Record<string, string>>(),
  locked: integer('locked', { mode: 'boolean' }).notNull().default(false),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  glossaryTermOrgIdx: index('idx_glossary_terms_org').on(t.orgId),
}));
