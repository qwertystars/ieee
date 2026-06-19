import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt } from './columns';
import { orgId } from './orgs';

export const users = sqliteTable(
  'users',
  {
    id: ulidPk(),
    orgId: orgId(),
    email: text('email').notNull(),
    name: text('name').notNull(),
    phone: text('phone'),
    role: text('role').notNull(),
    status: text('status', { enum: ['active', 'disabled', 'invited'] }).notNull().default('invited'),
    passwordHash: text('password_hash'),
    lastLoginAt: integer('last_login_at'),
    mfaSecret: text('mfa_secret'),
    createdAt: nowMs(),
    updatedAt: updatedAt(),
  },
  (table) => ({
    usersOrgIdx: index('idx_users_org').on(table.orgId),
    usersEmailIdx: index('idx_users_email').on(table.email),
  }),
);

export const roles = sqliteTable(
  'roles',
  {
    id: ulidPk(),
    orgId: orgId(),
    name: text('name').notNull(),
    system: integer('system', { mode: 'boolean' }).notNull().default(false),
    createdAt: nowMs(),
  },
  (table) => ({
    rolesOrgIdx: index('idx_roles_org').on(table.orgId),
  }),
);

export const memberships = sqliteTable(
  'memberships',
  {
    id: ulidPk(),
    userId: text('user_id').notNull().references(() => users.id),
    orgId: orgId(),
    roleId: text('role_id').notNull().references(() => roles.id),
    createdAt: nowMs(),
  },
  (table) => ({
    membershipsUserIdx: index('idx_memberships_user').on(table.userId),
    membershipsOrgIdx: index('idx_memberships_org').on(table.orgId),
  }),
);

export const rolePermissions = sqliteTable(
  'role_permissions',
  {
    id: ulidPk(),
    roleId: text('role_id').notNull().references(() => roles.id),
    action: text('action').notNull(),
    subject: text('subject').notNull(),
  },
  (table) => ({
    rolePermsRoleIdx: index('idx_role_perms_role').on(table.roleId),
  }),
);
