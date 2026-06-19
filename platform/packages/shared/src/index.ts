/**
 * Shared types and Zod schemas shared between worker and web.
 * Platform-wide conventions (FEATURES.md:35-43):
 * - IDs = ULID (26 chars, Crockford base32)
 * - Time = UTC epoch ms
 * - visibility ∈ {public, internal, sensitive}
 * - review_status ∈ {draft, reviewed, official}
 */

export const VISIBILITY = ['public', 'internal', 'sensitive'] as const;
export type Visibility = (typeof VISIBILITY)[number];

export const REVIEW_STATUS = ['draft', 'reviewed', 'official'] as const;
export type ReviewStatus = (typeof REVIEW_STATUS)[number];

export const ORG_KIND = ['tenant', 'agency', 'workspace'] as const;
export type OrgKind = (typeof ORG_KIND)[number];

export const DISASTER_TYPES = [
  'wildfire',
  'flood',
  'cyclone',
  'earthquake',
  'landslide',
  'chemical_spill',
  'heatwave',
  'power_outage',
  'civil_emergency',
  'disease_outbreak',
  'tsunami',
  'tornado',
  'avalanche',
  'drought',
  'building_collapse',
  'crowd_crush',
  'industrial_fire',
  'oil_spill',
  'radiological',
  'custom',
] as const;
export type DisasterType = (typeof DISASTER_TYPES)[number];

export const INCIDENT_SEVERITY = ['minor', 'moderate', 'severe', 'catastrophic'] as const;
export type IncidentSeverity = (typeof INCIDENT_SEVERITY)[number];

export const INCIDENT_STATUS = [
  'monitoring',
  'active',
  'contained',
  'resolved',
  'closed',
] as const;
export type IncidentStatus = (typeof INCIDENT_STATUS)[number];

export const DECLARATION_LEVEL = ['none', 'advisory', 'local', 'state', 'national'] as const;
export type DeclarationLevel = (typeof DECLARATION_LEVEL)[number];

/** GeoJSON geometry as stored in D1 (TEXT column, parsed as JSON). */
export type GeoJSONGeometry = {
  type: string;
  coordinates: number[] | number[][] | number[][][] | number[][][][];
};

/** Pagination wrapper used across all list endpoints. */
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

/** Standard API error response shape. */
export interface ApiError {
  error: {
    code: string;
    message: string;
    request_id: string;
    details?: Record<string, unknown>;
  };
}
