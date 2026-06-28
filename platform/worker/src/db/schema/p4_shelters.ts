import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

// T65: Extended shelter status snapshots (supplements shelters table in domain.ts)
export const shelterStatus = sqliteTable('shelter_status', {
  id: ulidPk(),
  orgId: orgId(),
  shelterId: text('shelter_id').notNull(),
  generatorFuel: integer('generator_fuel'), // fuel-hours remaining
  waterStatus: text('water_status', { enum: ['adequate', 'limited', 'critical', 'unknown'] }).notNull().default('unknown'),
  foodStatus: text('food_status', { enum: ['adequate', 'limited', 'critical', 'unknown'] }).notNull().default('unknown'),
  mealCapacityDay: integer('meal_capacity_day'),
  sanitationRatio: real('sanitation_ratio'), // Sphere ratio
  staffCount: integer('staff_count').notNull().default(0),
  securityPresent: integer('security_present', { mode: 'boolean' }).notNull().default(false),
  petSupport: integer('pet_support', { mode: 'boolean' }).notNull().default(false),
  accessibilitySupport: integer('accessibility_support', { mode: 'boolean' }).notNull().default(false),
  medicalSupport: integer('medical_support', { mode: 'boolean' }).notNull().default(false),
  notes: text('notes'),
  recordedAt: nowMs(),
}, (t) => ({
  shelterStatusOrgIdx: index('idx_shelter_status_org').on(t.orgId),
  shelterStatusShelterIdx: index('idx_shelter_status_shelter').on(t.shelterId),
}));

// T66: Shelter check-ins (person-level, split-name for privacy)
export const shelterCheckins = sqliteTable('shelter_checkins', {
  id: ulidPk(),
  orgId: orgId(),
  shelterId: text('shelter_id').notNull(),
  incidentId: text('incident_id').notNull(),
  personName: text('person_name').notNull(),
  personNameSplit: text('person_name_split'), // phonetic/normalized for matching
  bedNumber: text('bed_number'),
  familyGroupId: text('family_group_id'),
  vulnerable: integer('vulnerable', { mode: 'boolean' }).notNull().default(false),
  medicalNeeds: integer('medical_needs', { mode: 'boolean' }).notNull().default(false),
  dietaryNeeds: text('dietary_needs'),
  reunificationTriggerId: text('reunification_trigger_id'),
  checkedInAt: nowMs(),
  checkedOutAt: integer('checked_out_at'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
}, (t) => ({
  checkinOrgIdx: index('idx_shelter_checkins_org').on(t.orgId),
  checkinShelterIdx: index('idx_shelter_checkins_shelter').on(t.shelterId),
  checkinFamilyIdx: index('idx_shelter_checkins_family').on(t.familyGroupId),
}));

// T67: Shelter supply requests (ICS-213RR trigger to logistics)
export const shelterSupplyRequests = sqliteTable('shelter_supply_requests', {
  id: ulidPk(),
  orgId: orgId(),
  shelterId: text('shelter_id').notNull(),
  incidentId: text('incident_id').notNull(),
  itemType: text('item_type').notNull(),
  quantity: integer('quantity').notNull(),
  urgency: text('urgency', { enum: ['low', 'medium', 'high', 'critical'] }).notNull().default('medium'),
  status: text('status', { enum: ['requested', 'approved', 'dispatched', 'delivered', 'cancelled'] }).notNull().default('requested'),
  ics213rrRef: text('ics_213rr_ref'),
  notes: text('notes'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  supplyReqOrgIdx: index('idx_shelter_supply_req_org').on(t.orgId),
  supplyReqShelterIdx: index('idx_shelter_supply_req_shelter').on(t.shelterId),
  supplyReqStatusIdx: index('idx_shelter_supply_req_status').on(t.status),
}));

// T68: Shelter planning types
export const shelterPlans = sqliteTable('shelter_plans', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  shelterId: text('shelter_id'),
  planType: text('plan_type', {
    enum: ['donation_drop', 'temporary', 'mega', 'micro', 'special_needs', 'hospital_overflow'],
  }).notNull(),
  name: text('name').notNull(),
  location: text('location'),
  estimatedCapacity: integer('estimated_capacity'),
  hospitalId: text('hospital_id'),
  status: text('status', { enum: ['planned', 'approved', 'active', 'closed'] }).notNull().default('planned'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  shelterPlanOrgIdx: index('idx_shelter_plans_org').on(t.orgId),
  shelterPlanIncidentIdx: index('idx_shelter_plans_incident').on(t.incidentId),
  shelterPlanTypeIdx: index('idx_shelter_plans_type').on(t.planType),
}));

// T71: Missing persons (PFIF-compatible schema)
export const missingPersons = sqliteTable('missing_persons', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  fullName: text('full_name').notNull(),
  fullNameSplit: text('full_name_split'), // for fuzzy matching
  ageGroup: text('age_group', { enum: ['child', 'adult', 'senior', 'unknown'] }).notNull().default('unknown'),
  ageExact: integer('age_exact'),
  sex: text('sex', { enum: ['male', 'female', 'other', 'unknown'] }).notNull().default('unknown'),
  photoR2Key: text('photo_r2_key'),
  lastKnownLocation: text('last_known_location'),
  lastSeenAt: integer('last_seen_at'),
  medicalCondition: text('medical_condition'), // encrypted at rest
  vulnerability: text('vulnerability', { enum: ['none', 'medical', 'disability', 'child', 'elderly', 'pregnant'] }).notNull().default('none'),
  description: text('description'),
  contactName: text('contact_name'),
  contactPhone: text('contact_phone'),
  status: text('status', { enum: ['missing', 'found', 'reunited', 'deceased', 'closed'] }).notNull().default('missing'),
  assignedTo: text('assigned_to'),
  encryptedFields: text('encrypted_fields', { mode: 'json' }).$type<Record<string, string>>(),
  pfifId: text('pfif_id'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  missingOrgIdx: index('idx_missing_persons_org').on(t.orgId),
  missingIncidentIdx: index('idx_missing_persons_incident').on(t.incidentId),
  missingStatusIdx: index('idx_missing_persons_status').on(t.status),
  missingPfifIdx: index('idx_missing_persons_pfif').on(t.pfifId),
}));

// T71: Found persons
export const foundPersons = sqliteTable('found_persons', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  fullName: text('full_name').notNull(),
  fullNameSplit: text('full_name_split'),
  ageGroup: text('age_group', { enum: ['child', 'adult', 'senior', 'unknown'] }).notNull().default('unknown'),
  sex: text('sex', { enum: ['male', 'female', 'other', 'unknown'] }).notNull().default('unknown'),
  photoR2Key: text('photo_r2_key'),
  foundLocation: text('found_location'),
  foundAt: integer('found_at'),
  source: text('source', { enum: ['shelter', 'hospital', 'field', 'hotline', 'public'] }).notNull().default('shelter'),
  sourceRef: text('source_ref'),
  shelterCheckinId: text('shelter_checkin_id'),
  matchedMissingId: text('matched_missing_id'),
  matchStatus: text('match_status', { enum: ['pending', 'suggested', 'approved', 'rejected'] }).notNull().default('pending'),
  matchScore: real('match_score'),
  encryptedFields: text('encrypted_fields', { mode: 'json' }).$type<Record<string, string>>(),
  pfifId: text('pfif_id'),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  foundOrgIdx: index('idx_found_persons_org').on(t.orgId),
  foundIncidentIdx: index('idx_found_persons_incident').on(t.incidentId),
  foundMatchIdx: index('idx_found_persons_match').on(t.matchedMissingId),
}));

// T72: Missing person case notes
export const missingPersonNotes = sqliteTable('missing_person_notes', {
  id: ulidPk(),
  orgId: orgId(),
  missingPersonId: text('missing_person_id').notNull(),
  authorId: text('author_id').notNull(),
  note: text('note').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  noteMissingIdx: index('idx_missing_notes_person').on(t.missingPersonId),
}));

// T73: Reunification cases
export const reunificationCases = sqliteTable('reunification_cases', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  missingPersonId: text('missing_person_id').notNull(),
  foundPersonId: text('found_person_id'),
  status: text('status', { enum: ['initiated', 'notified', 'in_progress', 'completed', 'cancelled'] }).notNull().default('initiated'),
  reunificationCenterId: text('reunification_center_id'),
  qrCardR2Key: text('qr_card_r2_key'),
  safeAndWell: integer('safe_and_well', { mode: 'boolean' }).notNull().default(false),
  foreignNational: integer('foreign_national', { mode: 'boolean' }).notNull().default(false),
  embassyNotified: integer('embassy_notified', { mode: 'boolean' }).notNull().default(false),
  isDeceased: integer('is_deceased', { mode: 'boolean' }).notNull().default(false),
  approvedBy: text('approved_by'),
  approvedAt: integer('approved_at'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  reunificationOrgIdx: index('idx_reunification_org').on(t.orgId),
  reunificationMissingIdx: index('idx_reunification_missing').on(t.missingPersonId),
}));
