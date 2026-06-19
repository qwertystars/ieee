export { orgs, orgId } from './orgs';
export { users, memberships, roles, rolePermissions } from './users';
export { settings } from './settings';
export { apiKeys, sessions, devices } from './api_keys';

// Column helpers re-exported from columns.ts for backward compat
export { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';

// Table imports
import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt } from './columns';
import { orgId } from './orgs';
import { orgs } from './orgs';
import { users, memberships, roles, rolePermissions } from './users';
import { settings } from './settings';
import { apiKeys, sessions, devices } from './api_keys';

// ─── geo_index table (FEATURES.md:26 — H3 spatial index) ───────────────────

export const geo_index = sqliteTable(
  'geo_index',
  {
    entityType: text('entity_type').notNull(),
    entityId: text('entity_id').notNull(),
    h3: text('h3').notNull(),
    orgId: text('org_id').notNull(),
  },
  (table) => ({
    geoIndexIdx: index('idx_geo_index_h3').on(table.h3, table.entityType),
    geoIndexEntityIdx: index('idx_geo_index_entity').on(table.entityType, table.entityId),
    geoIndexOrgIdx: index('idx_geo_index_org').on(table.orgId),
  }),
);

// ─── idempotency table (FEATURES.md:41 — dedup on source+external_id) ─────

export const idempotency = sqliteTable(
  'idempotency',
  {
    id: text('id').primaryKey().notNull(),
    source: text('source').notNull(),
    externalId: text('external_id').notNull(),
    result: text('result', { mode: 'json' }).$type<unknown>(),
    createdAt: integer('created_at').notNull(),
  },
  (table) => ({
    idemSourceExtIdx: index('idx_idem_source_ext').on(table.source, table.externalId),
  }),
);

// ─── incidents table (minimal stub — full schema in T21) ──────────────────

export const incidents = sqliteTable(
  'incidents',
  {
    id: ulidPk(),
    orgId: orgId(),
    type: text('type').notNull(),
    severity: text('severity', {
      enum: ['minor', 'moderate', 'severe', 'catastrophic'],
    }).notNull(),
    status: text('status', {
      enum: ['monitoring', 'active', 'contained', 'resolved', 'closed'],
    }).notNull().default('monitoring'),
    title: text('title').notNull(),
    description: text('description'),
    geometry: text('geometry'),
    startsAt: integer('starts_at'),
    expectedEnd: integer('expected_end'),
    config: text('config', { mode: 'json' }).$type<Record<string, unknown>>(),
    declarationLevel: text('declaration_level', {
      enum: ['none', 'advisory', 'local', 'state', 'national'],
    }).notNull().default('none'),
    commandOwnerId: text('command_owner_id'),
    mergedIntoId: text('merged_into_id'),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (table) => ({
    incidentsOrgIdx: index('idx_incidents_org').on(table.orgId),
    incidentsStatusIdx: index('idx_incidents_status').on(table.status),
  }),
);

// ─── events table (audit hash-chain — FEATURES.md:40) ─────────────────────

export const events = sqliteTable(
  'events',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id'),
    actor: text('actor').notNull(),
    action: text('action').notNull(),
    entity: text('entity').notNull(),
    before: text('before', { mode: 'json' }).$type<unknown>(),
    after: text('after', { mode: 'json' }).$type<unknown>(),
    ts: integer('ts').notNull(),
    prevHash: text('prev_hash').notNull(),
    hash: text('hash').notNull(),
  },
  (table) => ({
    eventsOrgIdx: index('idx_events_org').on(table.orgId),
    eventsEntityIdx: index('idx_events_entity').on(table.entity, table.orgId),
    eventsTsIdx: index('idx_events_ts').on(table.ts),
  }),
);

// ─── incidentId helper (references incidents, stays in this file) ──────────

export const incidentId = () => text('incident_id').references(() => incidents.id);

// ─── Schema barrel export ───────────────────────────────────────────────────

export const schema = {
  geo_index,
  idempotency,
  orgs,
  users,
  memberships,
  roles,
  rolePermissions,
  settings,
  apiKeys,
  sessions,
  devices,
  incidents,
  events,
};
