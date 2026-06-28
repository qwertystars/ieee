import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

export const agencies = sqliteTable('agencies', {
  id: ulidPk(),
  orgId: orgId(),
  name: text('name').notNull(),
  capabilities: text('capabilities', { mode: 'json' }).$type<string[]>(),
  coverageArea: text('coverage_area'),
  contactName: text('contact_name'),
  contactPhone: text('contact_phone'),
  status: text('status', { enum: ['active', 'inactive', 'pending'] }).notNull().default('active'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  agencyOrgIdx: index('idx_agencies_org').on(t.orgId),
}));

export const mous = sqliteTable('mous', {
  id: ulidPk(),
  orgId: orgId(),
  agencyId: text('agency_id').notNull(),
  scope: text('scope').notNull(),
  expiry: integer('expiry'),
  docR2Key: text('doc_r2_key'),
  status: text('status', { enum: ['active', 'expired', 'terminated'] }).notNull().default('active'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  mouOrgIdx: index('idx_mous_org').on(t.orgId),
}));

export const incidentShares = sqliteTable('incident_shares', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  targetOrgId: text('target_org_id').notNull(),
  scope: text('scope', { mode: 'json' }).$type<string[]>(),
  status: text('status', { enum: ['pending', 'accepted', 'rejected', 'revoked'] }).notNull().default('pending'),
  createdAt: nowMs(),
}, (t) => ({
  incidentShareOrgIdx: index('idx_incident_shares_org').on(t.orgId),
  incidentShareIncidentIdx: index('idx_incident_shares_incident').on(t.incidentId),
}));

export const exercises = sqliteTable('exercises', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  name: text('name').notNull(),
  exerciseMode: text('exercise_mode', { enum: ['tabletop', 'functional', 'full_scale'] }).notNull().default('tabletop'),
  exerciseActive: integer('exercise_active', { mode: 'boolean' }).notNull().default(false),
  injectsR2Key: text('injects_r2_key'),
  startTime: integer('start_time'),
  endTime: integer('end_time'),
  status: text('status', { enum: ['planned', 'active', 'completed', 'cancelled'] }).notNull().default('planned'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  exerciseOrgIdx: index('idx_exercises_org').on(t.orgId),
}));

export const watches = sqliteTable('watches', {
  id: ulidPk(),
  orgId: orgId(),
  hazard: text('hazard').notNull(),
  geometry: text('geometry'),
  state: text('state', { enum: ['monitoring', 'advisory', 'watch', 'warning'] }).notNull().default('monitoring'),
  thresholdRule: text('threshold_rule'),
  triggeredAt: integer('triggered_at'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  watchOrgIdx: index('idx_watches_org').on(t.orgId),
}));

export const recoveryCases = sqliteTable('recovery_cases', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  householdRef: text('household_ref'),
  caseworkerId: text('caseworker_id'),
  stage: text('stage', { enum: ['intake', 'assessment', 'planning', 'implementation', 'monitoring', 'closed'] }).notNull().default('intake'),
  needs: text('needs', { mode: 'json' }).$type<string[]>(),
  cvaAmount: real('cva_amount'),
  cvaStatus: text('cva_status', { enum: ['none', 'pending', 'disbursed', 'rejected'] }).notNull().default('none'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  recoveryCaseOrgIdx: index('idx_recovery_cases_org').on(t.orgId),
  recoveryCaseIncidentIdx: index('idx_recovery_cases_incident').on(t.incidentId),
}));

export const costCodes = sqliteTable('cost_codes', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  code: text('code').notNull(),
  description: text('description'),
  femaCategory: text('fema_category', { enum: ['A', 'B', 'C', 'D', 'E', 'F', 'G'] }),
  createdAt: nowMs(),
}, (t) => ({
  costCodeOrgIdx: index('idx_cost_codes_org').on(t.orgId),
}));

export const costEntries = sqliteTable('cost_entries', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  costCodeId: text('cost_code_id').notNull(),
  amount: integer('amount').notNull(),
  currency: text('currency').notNull().default('USD'),
  source: text('source', { enum: ['time', 'equipment', 'purchase', 'contract'] }).notNull(),
  description: text('description'),
  ics214Ref: text('ics_214_ref'),
  rateCardId: text('rate_card_id'),
  hours: real('hours'),
  createdAt: nowMs(),
}, (t) => ({
  costEntryOrgIdx: index('idx_cost_entries_org').on(t.orgId),
  costEntryCodeIdx: index('idx_cost_entries_code').on(t.costCodeId),
}));

export const rateCards = sqliteTable('rate_cards', {
  id: ulidPk(),
  orgId: orgId(),
  role: text('role').notNull(),
  hourlyRate: integer('hourly_rate').notNull(),
  currency: text('currency').notNull().default('USD'),
  effectiveAt: integer('effective_at').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  rateCardOrgIdx: index('idx_rate_cards_org').on(t.orgId),
}));
