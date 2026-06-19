import { sqliteTable, text, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt } from './columns';
import { orgId } from './orgs';

export const settings = sqliteTable(
  'settings',
  {
    id: ulidPk(),
    scope: text('scope', { enum: ['org', 'incident', 'user'] }).notNull(),
    orgId: orgId(),
    incidentId: text('incident_id'),
    userId: text('user_id'),
    key: text('key').notNull(),
    value: text('value', { mode: 'json' }).$type<unknown>(),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (table) => ({
    settingsScopeIdx: index('idx_settings_scope').on(table.scope, table.orgId, table.key),
  }),
);
