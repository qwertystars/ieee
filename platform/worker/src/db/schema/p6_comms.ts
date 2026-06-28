import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

export const alertDeliveries = sqliteTable('alert_deliveries', {
  id: ulidPk(),
  orgId: orgId(),
  alertId: text('alert_id').notNull(),
  channel: text('channel', { enum: ['sms', 'voice', 'whatsapp', 'email', 'push', 'telegram'] }).notNull(),
  recipient: text('recipient').notNull(),
  status: text('status', { enum: ['pending', 'sent', 'delivered', 'failed', 'bounced'] }).notNull().default('pending'),
  providerMessageId: text('provider_message_id'),
  error: text('error'),
  attempts: integer('attempts').notNull().default(0),
  deliveredAt: integer('delivered_at'),
  createdAt: nowMs(),
}, (t) => ({
  deliveryOrgIdx: index('idx_alert_deliveries_org').on(t.orgId),
  deliveryAlertIdx: index('idx_alert_deliveries_alert').on(t.alertId),
  deliveryStatusIdx: index('idx_alert_deliveries_status').on(t.status),
}));

export const alertTemplates = sqliteTable('alert_templates', {
  id: ulidPk(),
  orgId: orgId(),
  name: text('name').notNull(),
  channel: text('channel').notNull(),
  subjectTemplate: text('subject_template'),
  bodyTemplate: text('body_template').notNull(),
  language: text('language').notNull().default('en'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  alertTemplateOrgIdx: index('idx_alert_templates_org').on(t.orgId),
}));

export const commsDrafts = sqliteTable('comms_drafts', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  draftType: text('draft_type', {
    enum: ['radio', 'ham_frequency', 'pa_script', 'social_post', 'website_banner', 'status_page', 'rumor_correction', 'misinformation', 'press_release', 'media_kit', 'widget', 'sitrep', 'faq', 'hotline_script', 'door_to_door', 'brevity', 'blackout_plan', 'offline_bulletin', 'poster'],
  }).notNull(),
  title: text('title').notNull(),
  content: text('content').notNull(),
  channel: text('channel'),
  language: text('language').notNull().default('en'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  commsDraftOrgIdx: index('idx_comms_drafts_org').on(t.orgId),
  commsDraftIncidentIdx: index('idx_comms_drafts_incident').on(t.incidentId),
  commsDraftTypeIdx: index('idx_comms_drafts_type').on(t.draftType),
}));

export const publicSubscriptions = sqliteTable('public_subscriptions', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  phone: text('phone'),
  email: text('email'),
  geoPolygon: text('geo_polygon'),
  channels: text('channels', { mode: 'json' }).$type<string[]>(),
  language: text('language').notNull().default('en'),
  active: integer('active', { mode: 'boolean' }).notNull().default(true),
  createdAt: nowMs(),
}, (t) => ({
  subscriptionOrgIdx: index('idx_public_subs_org').on(t.orgId),
  subscriptionIncidentIdx: index('idx_public_subs_incident').on(t.incidentId),
}));

export const webhookSubscriptions = sqliteTable('webhook_subscriptions', {
  id: ulidPk(),
  orgId: orgId(),
  url: text('url').notNull(),
  events: text('events', { mode: 'json' }).$type<string[]>().notNull(),
  secret: text('secret').notNull(),
  active: integer('active', { mode: 'boolean' }).notNull().default(true),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  webhookSubOrgIdx: index('idx_webhook_subs_org').on(t.orgId),
}));

export const webhookDeliveries = sqliteTable('webhook_deliveries', {
  id: ulidPk(),
  orgId: orgId(),
  subscriptionId: text('subscription_id').notNull(),
  event: text('event').notNull(),
  payload: text('payload', { mode: 'json' }).$type<unknown>(),
  status: text('status', { enum: ['pending', 'delivered', 'failed', 'retry'] }).notNull().default('pending'),
  attempts: integer('attempts').notNull().default(0),
  responseCode: integer('response_code'),
  error: text('error'),
  deliveredAt: integer('delivered_at'),
  createdAt: nowMs(),
}, (t) => ({
  webhookDeliveryOrgIdx: index('idx_webhook_deliveries_org').on(t.orgId),
  webhookDeliverySubIdx: index('idx_webhook_deliveries_sub').on(t.subscriptionId),
}));
