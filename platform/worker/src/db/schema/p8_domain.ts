import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

// T112: Road graph edges
export const roadEdges = sqliteTable('road_edges', {
  id: ulidPk(),
  orgId: orgId(),
  regionId: text('region_id').notNull(),
  fromNode: text('from_node').notNull(),
  toNode: text('to_node').notNull(),
  length: real('length').notNull(),
  capacity: integer('capacity').notNull().default(100),
  oneway: integer('oneway', { mode: 'boolean' }).notNull().default(false),
  hazardWeight: real('hazard_weight').notNull().default(0),
  contraflow: integer('contraflow', { mode: 'boolean' }).notNull().default(false),
  createdAt: nowMs(),
}, (t) => ({
  roadEdgeOrgIdx: index('idx_road_edges_org').on(t.orgId),
  roadEdgeRegionIdx: index('idx_road_edges_region').on(t.regionId),
  roadEdgeFromIdx: index('idx_road_edges_from').on(t.fromNode),
  roadEdgeToIdx: index('idx_road_edges_to').on(t.toNode),
}));

// T113: Evacuation zones
export const evacZones = sqliteTable('evac_zones', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  zoneName: text('zone_name').notNull(),
  geometry: text('geometry').notNull(),
  status: text('status', { enum: ['advisory', 'ordered', 'cleared', 'nogo'] }).notNull().default('advisory'),
  priority: integer('priority').notNull().default(1),
  estimatedPop: integer('estimated_pop'),
  routeR2Key: text('route_r2_key'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  evacZoneOrgIdx: index('idx_evac_zones_org').on(t.orgId),
  evacZoneIncidentIdx: index('idx_evac_zones_incident').on(t.incidentId),
}));

// T116: Medical facilities
export const medicalFacilities = sqliteTable('medical_facilities', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  name: text('name').notNull(),
  type: text('type', { enum: ['hospital', 'clinic', 'field_hospital', 'mobile_unit' ] }).notNull(),
  geo: text('geo'),
  totalBeds: integer('total_beds').notNull().default(0),
  availableBeds: integer('available_beds').notNull().default(0),
  icuBeds: integer('icu_beds').notNull().default(0),
  erBeds: integer('er_beds').notNull().default(0),
  ambulances: integer('ambulances').notNull().default(0),
  status: text('status', { enum: ['open', 'diverted', 'full', 'closed'] }).notNull().default('open'),
  fhirId: text('fhir_id'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  medFacOrgIdx: index('idx_medical_facilities_org').on(t.orgId),
}));

// T116: Triage patients
export const triagePatients = sqliteTable('triage_patients', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  facilityId: text('facility_id'),
  qrWristband: text('qr_wristband'),
  triageCategory: text('triage_category', { enum: ['immediate', 'delayed', 'minor', 'expectant'] }).notNull(),
  severity: text('severity', { enum: ['critical', 'serious', 'moderate', 'minor'] }).notNull().default('minor'),
  name: text('name'),
  age: integer('age'),
  sex: text('sex'),
  transportStatus: text('transport_status', { enum: ['pending', 'transporting', 'arrived', 'admitted'] }).notNull().default('pending'),
  transportRequestId: text('transport_request_id'),
  mciMode: integer('mci_mode', { mode: 'boolean' }).notNull().default(false),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  triagePatientOrgIdx: index('idx_triage_patients_org').on(t.orgId),
  triagePatientIncidentIdx: index('idx_triage_patients_incident').on(t.incidentId),
}));

// T118: Logistics items
export const logisticsItems = sqliteTable('logistics_items', {
  id: ulidPk(),
  orgId: orgId(),
  sku: text('sku').notNull(),
  name: text('name').notNull(),
  category: text('category').notNull(),
  unit: text('unit').notNull().default('each'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  logisticsItemOrgIdx: index('idx_logistics_items_org').on(t.orgId),
}));

// T118: Stock levels
export const logisticsStock = sqliteTable('logistics_stock', {
  id: ulidPk(),
  orgId: orgId(),
  itemId: text('item_id').notNull(),
  locationId: text('location_id').notNull(),
  qty: integer('qty').notNull().default(0),
  lot: text('lot'),
  expiry: integer('expiry'),
  updatedAt: updatedAt(),
}, (t) => ({
  logisticsStockOrgIdx: index('idx_logistics_stock_org').on(t.orgId),
  logisticsStockItemIdx: index('idx_logistics_stock_item').on(t.itemId),
}));

// T118: Movements ledger (append-only, idempotent)
export const logisticsMovements = sqliteTable('logistics_movements', {
  id: ulidPk(),
  orgId: orgId(),
  itemId: text('item_id').notNull(),
  fromLocation: text('from_location'),
  toLocation: text('to_location'),
  qty: integer('qty').notNull(),
  lot: text('lot'),
  movementType: text('movement_type', { enum: ['receive', 'transfer', 'dispatch', 'consume', 'adjust', 'return'] }).notNull(),
  idempotencyKey: text('idempotency_key').notNull(),
  reference: text('reference'),
  createdAt: nowMs(),
}, (t) => ({
  logisticsMovementOrgIdx: index('idx_logistics_movements_org').on(t.orgId),
  logisticsMovementItemIdx: index('idx_logistics_movements_item').on(t.itemId),
  logisticsMovementIdemIdx: index('idx_logistics_movements_idem').on(t.idempotencyKey),
}));

// T119: Resource requests (ICS-213RR)
export const resourceRequests = sqliteTable('resource_requests', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id').notNull(),
  itemType: text('item_type').notNull(),
  quantity: integer('quantity').notNull(),
  urgency: text('urgency', { enum: ['low', 'medium', 'high', 'critical'] }).notNull().default('medium'),
  status: text('status', { enum: ['requested', 'approved', 'allocated', 'dispatched', 'delivered', 'returned', 'cancelled'] }).notNull().default('requested'),
  requestedBy: text('requested_by'),
  approvedBy: text('approved_by'),
  ics213rrRef: text('ics_213rr_ref'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  resourceRequestOrgIdx: index('idx_resource_requests_org').on(t.orgId),
  resourceRequestIncidentIdx: index('idx_resource_requests_incident').on(t.incidentId),
  resourceRequestStatusIdx: index('idx_resource_requests_status').on(t.status),
}));

// T123: Infrastructure assets
export const infraAssets = sqliteTable('infra_assets', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  type: text('type').notNull(),
  name: text('name').notNull(),
  geo: text('geo'),
  status: text('status', { enum: ['operational', 'degraded', 'failed', 'restored', 'unknown'] }).notNull().default('unknown'),
  restoreEta: integer('restore_eta'),
  parentId: text('parent_id'),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  infraAssetOrgIdx: index('idx_infra_assets_org').on(t.orgId),
  infraAssetIncidentIdx: index('idx_infra_assets_incident').on(t.incidentId),
  infraAssetTypeIdx: index('idx_infra_assets_type').on(t.type),
}));

// T123: Asset dependencies (DAG edges)
export const infraAssetDeps = sqliteTable('infra_asset_deps', {
  id: ulidPk(),
  orgId: orgId(),
  parentId: text('parent_id').notNull(),
  childId: text('child_id').notNull(),
  createdAt: nowMs(),
}, (t) => ({
  infraDepParentIdx: index('idx_infra_deps_parent').on(t.parentId),
  infraDepChildIdx: index('idx_infra_deps_child').on(t.childId),
}));
