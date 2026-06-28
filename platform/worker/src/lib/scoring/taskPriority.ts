// T49/T52: Auto-priority scoring + auto-assignment.
// Deterministic score = severity × vulnerability × age decay × proximity.

export interface ScoringInput {
  severity: number; // 0-4
  vulnerability: number; // 0-1 (elderly/medical/child weight)
  ageMs: number; // ms since creation
  proximityKm: number | null; // distance to nearest responder
}

export function taskPriorityScore(input: ScoringInput): number {
  const ageDecay = Math.exp(-input.ageMs / (6 * 3600 * 1000)); // 6h half-life
  const proximityFactor = input.proximityKm === null
    ? 0.5
    : Math.max(0, 1 - input.proximityKm / 50); // 50km = 0
  const severity = Math.max(0, Math.min(4, input.severity));
  const vulnerability = Math.max(0, Math.min(1, input.vulnerability));
  return severity * vulnerability * ageDecay * proximityFactor;
}

// T58: Help request priority scoring (severity × vulnerability × age decay)
export function helpPriorityScore(input: {
  severity: number;
  vulnerability: number;
  ageMs: number;
}): number {
  const ageDecay = Math.exp(-input.ageMs / (3 * 3600 * 1000)); // 3h half-life
  return Math.max(0, Math.min(4, input.severity)) * Math.max(0, Math.min(1, input.vulnerability)) * ageDecay;
}

export function priorityLabel(score: number): 'low' | 'medium' | 'high' | 'critical' {
  if (score >= 3) return 'critical';
  if (score >= 2) return 'high';
  if (score >= 1) return 'medium';
  return 'low';
}

// T49: Auto-assign — nearest available responder with matching skill.
// Uses H3 distance when available; falls back to haversine on geo.
export interface AssignCandidate {
  responderId: string;
  distanceKm: number;
  hasSkill: boolean;
  status: string;
}

export function pickAssignee(candidates: AssignCandidate[]): AssignCandidate | null {
  const available = candidates.filter((c) => c.status === 'available' && c.hasSkill);
  if (available.length === 0) return null;
  available.sort((a, b) => a.distanceKm - b.distanceKm);
  return available[0] ?? null;
}

// T51: Conflict detection — same H3 cell + kind + time window
export function isConflict(
  existing: { h3?: string; kind: string; createdAt: number }[],
  candidate: { h3?: string; kind: string; createdAt: number },
  windowMs: number = 3600 * 1000,
): boolean {
  if (!candidate.h3) return false;
  return existing.some(
    (e) => e.h3 === candidate.h3 && e.kind === candidate.kind && Math.abs(e.createdAt - candidate.createdAt) < windowMs,
  );
}
