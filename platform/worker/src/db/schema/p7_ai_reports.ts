import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

export const aiCalls = sqliteTable('ai_calls', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  promptName: text('prompt_name').notNull(),
  promptVersion: integer('prompt_version').notNull().default(1),
  provider: text('provider').notNull(),
  model: text('model').notNull(),
  inputTokens: integer('input_tokens'),
  outputTokens: integer('output_tokens'),
  latencyMs: integer('latency_ms'),
  cost: real('cost'),
  success: integer('success', { mode: 'boolean' }).notNull().default(true),
  error: text('error'),
  createdAt: nowMs(),
}, (t) => ({
  aiCallOrgIdx: index('idx_ai_calls_org').on(t.orgId),
  aiCallPromptIdx: index('idx_ai_calls_prompt').on(t.promptName),
}));

export const prompts = sqliteTable('prompts', {
  id: ulidPk(),
  orgId: orgId(),
  name: text('name').notNull(),
  version: integer('version').notNull().default(1),
  body: text('body').notNull(),
  schema: text('schema', { mode: 'json' }).$type<Record<string, unknown>>(),
  temperature: real('temperature').default(0.7),
  active: integer('active', { mode: 'boolean' }).notNull().default(true),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  promptOrgIdx: index('idx_prompts_org').on(t.orgId),
  promptNameIdx: index('idx_prompts_name').on(t.name),
}));

export const aiOutputs = sqliteTable('ai_outputs', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  promptName: text('prompt_name').notNull(),
  output: text('output', { mode: 'json' }).$type<unknown>(),
  confidence: real('confidence'),
  citations: text('citations', { mode: 'json' }).$type<string[]>(),
  hallucinationFlag: integer('hallucination_flag', { mode: 'boolean' }).notNull().default(false),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  approvedBy: text('approved_by'),
  approvedAt: integer('approved_at'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  aiOutputOrgIdx: index('idx_ai_outputs_org').on(t.orgId),
  aiOutputIncidentIdx: index('idx_ai_outputs_incident').on(t.incidentId),
}));

export const reports = sqliteTable('reports', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  title: text('title').notNull(),
  reportType: text('report_type').notNull(),
  templateId: text('template_id'),
  contentMd: text('content_md'),
  contentHtml: text('content_html'),
  r2Key: text('r2_key'),
  shareToken: text('share_token'),
  shareExpiry: integer('share_expiry'),
  scheduledAt: integer('scheduled_at'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  version: integer('version').notNull().default(1),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  reportOrgIdx: index('idx_reports_org').on(t.orgId),
  reportIncidentIdx: index('idx_reports_incident').on(t.incidentId),
  reportTypeIdx: index('idx_reports_type').on(t.reportType),
}));

export const reportTemplates = sqliteTable('report_templates', {
  id: ulidPk(),
  orgId: orgId(),
  name: text('name').notNull(),
  reportType: text('report_type').notNull(),
  templateMd: text('template_md').notNull(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  reportTemplateOrgIdx: index('idx_report_templates_org').on(t.orgId),
}));
