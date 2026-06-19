import { text, integer } from 'drizzle-orm/sqlite-core';

export const ulidPk = () => text('id').primaryKey().notNull();
export const nowMs = () => integer('created_at').notNull();
export const updatedAt = () => integer('updated_at').notNull();
export const visibility = () =>
  text('visibility', { enum: ['public', 'internal', 'sensitive'] }).notNull().default('internal');
export const reviewStatus = () =>
  text('review_status', { enum: ['draft', 'reviewed', 'official'] }).notNull().default('draft');
