import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

// T49: Extended task fields (supplements tasks table in domain.ts via ALTER migration)
// task_extras holds the columns not in the original tasks table.
export const taskExtras = sqliteTable('task_extras', {
  taskId: text('task_id').primaryKey().notNull(),
  kind: text('kind').notNull().default('general'),
  geo: text('geo'),
  assigneeUserId: text('assignee_user_id'),
  slaAt: integer('sla_at'),
  parentId: text('parent_id'),
  dependencies: text('dependencies', { mode: 'json' }).$type<string[]>(),
  riskScore: real('risk_score').notNull().default(0),
  impactScore: real('impact_score').notNull().default(0),
  urgencyScore: real('urgency_score').notNull().default(0),
  publicVisible: integer('public_visible', { mode: 'boolean' }).notNull().default(false),
  checklist: text('checklist', { mode: 'json' }).$type<ChecklistItem[]>(),
  completionProof: text('completion_proof', { mode: 'json' }).$type<unknown>(),
  verifiedBy: text('verified_by'),
  verifiedAt: integer('verified_at'),
  h3: text('h3'),
});

export interface ChecklistItem {
  label: string;
  done: boolean;
}

// T50: Task linking, comments, attachments, templates
export const taskLinks = sqliteTable('task_links', {
  id: ulidPk(),
  orgId: orgId(),
  taskId: text('task_id').notNull(),
  targetType: text('target_type').notNull(),
  targetId: text('target_id').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  taskLinkTaskIdx: index('idx_task_links_task').on(t.taskId),
  taskLinkTargetIdx: index('idx_task_links_target').on(t.targetType, t.targetId),
}));

export const taskComments = sqliteTable('task_comments', {
  id: ulidPk(),
  orgId: orgId(),
  taskId: text('task_id').notNull(),
  authorId: text('author_id').notNull(),
  body: text('body').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  taskCommentTaskIdx: index('idx_task_comments_task').on(t.taskId),
}));

export const taskAttachments = sqliteTable('task_attachments', {
  id: ulidPk(),
  orgId: orgId(),
  taskId: text('task_id').notNull(),
  r2Key: text('r2_key').notNull(),
  name: text('name').notNull(),
  kind: text('kind').notNull().default('file'),
  uploadedBy: text('uploaded_by').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  taskAttachmentTaskIdx: index('idx_task_attachments_task').on(t.taskId),
}));

export const taskTemplates = sqliteTable('task_templates', {
  id: ulidPk(),
  orgId: orgId(),
  name: text('name').notNull(),
  kind: text('kind').notNull().default('general'),
  title: text('title').notNull(),
  description: text('description'),
  priority: text('priority').notNull().default('medium'),
  checklist: text('checklist', { mode: 'json' }).$type<ChecklistItem[]>(),
  recurringCron: text('recurring_cron'),
  createdAt: nowMs(),
});

// T53: Field responder registries
export const responders = sqliteTable('responders', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  userId: text('user_id'),
  name: text('name').notNull(),
  kind: text('kind', { enum: ['responder', 'volunteer', 'medical', 'k9'] }).notNull().default('responder'),
  status: text('status', { enum: ['available', 'dispatched', 'on_scene', 'off_duty', 'break'] }).notNull().default('available'),
  skills: text('skills', { mode: 'json' }).$type<string[]>(),
  certifications: text('certifications', { mode: 'json' }).$type<CertRecord[]>(),
  contactPhone: text('contact_phone'),
  currentLocation: text('current_location'),
  teamId: text('team_id'),
  availabilityStart: integer('availability_start'),
  availabilityEnd: integer('availability_end'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  responderOrgIdx: index('idx_responders_org').on(t.orgId),
  responderIncidentIdx: index('idx_responders_incident').on(t.incidentId),
  responderStatusIdx: index('idx_responders_status').on(t.status),
}));

export interface CertRecord {
  name: string;
  expiry: number | null;
  docKey: string | null;
}

export const vehicles = sqliteTable('vehicles', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  name: text('name').notNull(),
  type: text('type').notNull().default('truck'),
  capacity: integer('capacity').notNull().default(4),
  status: text('status', { enum: ['available', 'in_use', 'maintenance', 'offline'] }).notNull().default('available'),
  teamId: text('team_id'),
  fuelLevel: integer('fuel_level'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  vehicleOrgIdx: index('idx_vehicles_org').on(t.orgId),
}));

export const equipment = sqliteTable('equipment', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  name: text('name').notNull(),
  category: text('category').notNull().default('general'),
  status: text('status', { enum: ['available', 'checked_out', 'maintenance'] }).notNull().default('available'),
  checkedOutBy: text('checked_out_by'),
  checkedOutAt: integer('checked_out_at'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  equipmentOrgIdx: index('idx_equipment_org').on(t.orgId),
}));

// T54: Shifts and check-in/out (ICS-211)
export const shifts = sqliteTable('shifts', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  responderId: text('responder_id').notNull(),
  teamId: text('team_id'),
  role: text('role'),
  startTime: integer('start_time').notNull(),
  endTime: integer('end_time'),
  buddyId: text('buddy_id'),
  status: text('status', { enum: ['scheduled', 'active', 'completed', 'cancelled'] }).notNull().default('scheduled'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  shiftOrgIdx: index('idx_shifts_org').on(t.orgId),
  shiftResponderIdx: index('idx_shifts_responder').on(t.responderId),
}));

export const fieldCheckins = sqliteTable('field_checkins', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  responderId: text('responder_id').notNull(),
  type: text('type', { enum: ['check_in', 'check_out'] }).notNull(),
  location: text('location'),
  shiftId: text('shift_id'),
  timestamp: integer('timestamp').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  checkinOrgIdx: index('idx_field_checkins_org').on(t.orgId),
  checkinResponderIdx: index('idx_field_checkins_responder').on(t.responderId),
}));

// T55: Field reports (Form Builder)
export const fieldReports = sqliteTable('field_reports', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  responderId: text('responder_id').notNull(),
  formType: text('form_type', {
    enum: ['checklist', 'triage', 'damage', 'trapped', 'road_blockage', 'infrastructure', 'dosimeter', 'k9', 'par'],
  }).notNull(),
  taskId: text('task_id'),
  data: text('data', { mode: 'json' }).$type<Record<string, unknown>>(),
  attachments: text('attachments', { mode: 'json' }).$type<string[]>(),
  location: text('location'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  fieldReportOrgIdx: index('idx_field_reports_org').on(t.orgId),
  fieldReportIncidentIdx: index('idx_field_reports_incident').on(t.incidentId),
  fieldReportTypeIdx: index('idx_field_reports_type').on(t.formType),
}));

// T57: Help requests
export const helpRequests = sqliteTable('help_requests', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  source: text('source', {
    enum: ['public', 'sms', 'email', 'whatsapp', 'telegram', 'ivr', 'hotline', 'field'],
  }).notNull().default('public'),
  externalId: text('external_id'),
  category: text('category', {
    enum: ['rescue', 'medical', 'food', 'water', 'shelter', 'transport', 'missing', 'trapped', 'animal', 'accessibility', 'other'],
  }).notNull().default('other'),
  description: text('description'),
  geo: text('geo'),
  address: text('address'),
  contactName: text('contact_name'),
  contactPhone: text('contact_phone'),
  peopleCount: integer('people_count').notNull().default(1),
  priority: text('priority', { enum: ['low', 'medium', 'high', 'critical'] }).notNull().default('medium'),
  score: real('score').notNull().default(0),
  status: text('status', {
    enum: ['pending', 'triaged', 'assigned', 'in_progress', 'resolved', 'closed', 'duplicate'],
  }).notNull().default('pending'),
  confidence: real('confidence').notNull().default(0.5),
  mergedIntoId: text('merged_into_id'),
  assignedTaskId: text('assigned_task_id'),
  repeatCaller: integer('repeat_caller', { mode: 'boolean' }).notNull().default(false),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  helpReqOrgIdx: index('idx_help_requests_org').on(t.orgId),
  helpReqIncidentIdx: index('idx_help_requests_incident').on(t.incidentId),
  helpReqStatusIdx: index('idx_help_requests_status').on(t.status),
  helpReqSourceExtIdx: index('idx_help_requests_source_ext').on(t.source, t.externalId),
}));

// T60: Volunteer extends responders — volunteer-specific fields
export const volunteerProfiles = sqliteTable('volunteer_profiles', {
  id: ulidPk(),
  orgId: orgId(),
  responderId: text('responder_id').notNull(),
  verificationStatus: text('verification_status', {
    enum: ['pending', 'verified', 'rejected', 'expired'],
  }).notNull().default('pending'),
  trainingStatus: text('training_status', {
    enum: ['not_started', 'in_progress', 'completed', 'expired'],
  }).notNull().default('not_started'),
  quizScore: real('quiz_score'),
  backgroundStatus: text('background_status', { enum: ['pending', 'clear', 'flag'] }).notNull().default('pending'),
  minorGuardianConsent: integer('minor_guardian_consent', { mode: 'boolean' }),
  insuranceFlag: integer('insurance_flag', { mode: 'boolean' }).notNull().default(false),
  safetyBriefingCompleted: integer('safety_briefing', { mode: 'boolean' }).notNull().default(false),
  totalHours: real('total_hours').notNull().default(0),
  supervisorId: text('supervisor_id'),
  orgAffiliation: text('org_affiliation'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  volunteerOrgIdx: index('idx_volunteer_profiles_org').on(t.orgId),
  volunteerResponderIdx: index('idx_volunteer_profiles_responder').on(t.responderId),
}));

// T62: Community org registry
export const communityOrgs = sqliteTable('community_orgs', {
  id: ulidPk(),
  orgId: orgId(),
  name: text('name').notNull(),
  type: text('type', { enum: ['ngo', 'community', 'faith', 'mutual_aid', 'government', 'private'] }).notNull().default('ngo'),
  capabilities: text('capabilities', { mode: 'json' }).$type<string[]>(),
  contactName: text('contact_name'),
  contactPhone: text('contact_phone'),
  coverageArea: text('coverage_area'),
  mouId: text('mou_id'),
  status: text('status', { enum: ['active', 'inactive', 'pending'] }).notNull().default('active'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  communityOrgIdx: index('idx_community_orgs_org').on(t.orgId),
}));
