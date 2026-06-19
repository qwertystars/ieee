import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt } from './columns';

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

// FEATURES.md:37 — org_id on every org-scoped table, resolved server-side.
export const orgId = () => text('org_id').notNull().references(() => orgs.id);
