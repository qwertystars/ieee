import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';
import { orgId } from './orgs';
import { ulidPk, nowMs } from './columns';

export const notifications = sqliteTable(
  'notifications',
  {
    id: ulidPk(),
    orgId: orgId(),
    userId: text('user_id').notNull(),
    kind: text('kind').notNull(),
    title: text('title').notNull(),
    body: text('body'),
    payload: text('payload', { mode: 'json' }).$type<unknown>(),
    readAt: integer('read_at'),
    createdAt: nowMs(),
  },
  (table) => ({
    notifUserIdx: index('idx_notif_user').on(table.userId, table.readAt),
    notifOrgIdx: index('idx_notif_org').on(table.orgId),
  }),
);
