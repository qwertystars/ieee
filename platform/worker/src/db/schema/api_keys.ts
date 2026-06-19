import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs } from './columns';
import { orgId } from './orgs';
import { users } from './users';

export const devices = sqliteTable(
  'devices',
  {
    id: ulidPk(),
    userId: text('user_id').notNull().references(() => users.id),
    userAgent: text('user_agent'),
    lastIp: text('last_ip'),
    fingerprint: text('fingerprint'),
    lastSeenAt: integer('last_seen_at').notNull(),
    createdAt: nowMs(),
  },
  (table) => ({
    devicesUserIdx: index('idx_devices_user').on(table.userId),
  }),
);

export const sessions = sqliteTable(
  'sessions',
  {
    id: ulidPk(),
    userId: text('user_id').notNull().references(() => users.id),
    deviceId: text('device_id').references(() => devices.id),
    tokenHash: text('token_hash').notNull(),
    expiresAt: integer('expires_at').notNull(),
    createdAt: nowMs(),
  },
  (table) => ({
    sessionsUserIdx: index('idx_sessions_user').on(table.userId),
    sessionsTokenIdx: index('idx_sessions_token').on(table.tokenHash),
  }),
);

export const apiKeys = sqliteTable(
  'api_keys',
  {
    id: ulidPk(),
    orgId: orgId(),
    prefix: text('prefix').notNull(),
    hash: text('hash').notNull(),
    scopes: text('scopes', { mode: 'json' }).$type<string[]>(),
    lastUsedAt: integer('last_used_at'),
    createdAt: nowMs(),
    revokedAt: integer('revoked_at'),
  },
  (table) => ({
    apiKeysPrefixIdx: index('idx_api_keys_prefix').on(table.prefix),
    apiKeysOrgIdx: index('idx_api_keys_org').on(table.orgId),
  }),
);
