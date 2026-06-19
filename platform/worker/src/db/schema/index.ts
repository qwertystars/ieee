import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';

// ─── Column helpers (FEATURES.md:38 — ULID IDs, UTC epoch ms) ──────────────

/** ULID primary key — 26-char Crockford base32, monotonic. */
export const ulidPk = () =>
  text('id')
    .primaryKey()
    .notNull();

/** UTC epoch milliseconds (FEATURES.md:38). */
export const nowMs = () => integer('created_at').notNull();

/** Updated-at column, defaults to created_at. */
export const updatedAt = () => integer('updated_at').notNull();

/** org_id column — present on EVERY org-scoped table (FEATURES.md:37). Indexed. */
export const orgId = () =>
  text('org_id')
    .notNull()
    .references(() => orgs.id);

/** incident_id column — nullable, present on incident-scoped tables. Indexed. */
export const incidentId = () =>
  text('incident_id')
    .references(() => incidents.id);

/** visibility enum column (FEATURES.md:39). */
export const visibility = () =>
  text('visibility', { enum: ['public', 'internal', 'sensitive'] })
    .notNull()
    .default('internal');

/** review_status enum column (FEATURES.md:39). */
export const reviewStatus = () =>
  text('review_status', { enum: ['draft', 'reviewed', 'official'] })
    .notNull()
    .default('draft');

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

// ─── orgs table (minimal stub — full schema in T7) ─────────────────────────

export const orgs = sqliteTable('orgs', {
  id: ulidPk(),
  name: text('name').notNull(),
  slug: text('slug').notNull().unique(),
  kind: text('kind', { enum: ['tenant', 'agency', 'workspace'] }).notNull().default('tenant'),
  branding: text('branding', { mode: 'json' }).$type<Record<string, unknown>>(),
  settings: text('settings', { mode: 'json' }).$type<Record<string, unknown>>(),
  dataRegion: text('data_region'),
  locked: integer('locked', { mode: 'boolean' }).notNull().default(false),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
});

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

// ─── events table (audit hash-chain — FEATURES.md:40, full impl in T5) ───

export const events = sqliteTable(
  'events',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: incidentId(),
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

// ─── Schema barrel export ───────────────────────────────────────────────────

export const schema = {
  geo_index,
  orgs,
  incidents,
  events,
};
