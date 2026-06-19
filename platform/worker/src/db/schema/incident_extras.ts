import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt } from './columns';
import { orgId } from './orgs';

export const incidentAttachments = sqliteTable(
  'incident_attachments',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    r2Key: text('r2_key').notNull(),
    name: text('name').notNull(),
    kind: text('kind').notNull(),
    createdAt: nowMs(),
  },
  (t) => ({ incAttIncIdx: index('idx_inc_att_inc').on(t.incidentId) }),
);

export const incidentNotes = sqliteTable(
  'incident_notes',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    authorId: text('author_id').notNull(),
    body: text('body').notNull(),
    createdAt: nowMs(),
  },
  (t) => ({ incNoteIncIdx: index('idx_inc_note_inc').on(t.incidentId) }),
);

export const incidentTags = sqliteTable(
  'incident_tags',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    tag: text('tag').notNull(),
    createdAt: nowMs(),
  },
  (t) => ({ incTagIncIdx: index('idx_inc_tag_inc').on(t.incidentId, t.tag) }),
);

export const incidentTeams = sqliteTable(
  'incident_teams',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    teamId: text('team_id').notNull(),
    role: text('role'),
    createdAt: nowMs(),
  },
  (t) => ({ incTeamIncIdx: index('idx_inc_team_inc').on(t.incidentId) }),
);

export const incidentLinks = sqliteTable(
  'incident_links',
  {
    id: ulidPk(),
    parentId: text('parent_id').notNull(),
    childId: text('child_id').notNull(),
    kind: text('kind').notNull(),
    createdAt: nowMs(),
  },
  (t) => ({ incLinkParentIdx: index('idx_inc_link_parent').on(t.parentId) }),
);

export const incidentTemplates = sqliteTable(
  'incident_templates',
  {
    id: ulidPk(),
    orgId: orgId(),
    name: text('name').notNull(),
    type: text('type').notNull(),
    config: text('config', { mode: 'json' }).$type<Record<string, unknown>>(),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (t) => ({ incTplOrgIdx: index('idx_inc_tpl_org').on(t.orgId) }),
);

export const mapLayers = sqliteTable(
  'map_layers',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id'),
    name: text('name').notNull(),
    kind: text('kind').notNull(),
    source: text('source').notNull(),
    style: text('style', { mode: 'json' }).$type<Record<string, unknown>>(),
    visibility: text('visibility', { enum: ['public', 'internal', 'sensitive'] }).notNull().default('internal'),
    reviewStatus: text('review_status', { enum: ['draft', 'reviewed', 'official'] }).notNull().default('draft'),
    sort: integer('sort').notNull().default(0),
    version: integer('version').notNull().default(1),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (t) => ({ mapLayerIncIdx: index('idx_map_layer_inc').on(t.incidentId) }),
);

export const mapZones = sqliteTable(
  'map_zones',
  {
    id: ulidPk(),
    orgId: orgId(),
    incidentId: text('incident_id').notNull(),
    zoneType: text('zone_type').notNull(),
    geometry: text('geometry').notNull(),
    style: text('style', { mode: 'json' }).$type<Record<string, unknown>>(),
    reviewStatus: text('review_status', { enum: ['draft', 'reviewed', 'official'] }).notNull().default('draft'),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (t) => ({ mapZoneIncIdx: index('idx_map_zone_inc').on(t.incidentId, t.zoneType) }),
);
