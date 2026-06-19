export class SerializationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SerializationError';
  }
}

const PII_FIELDS: ReadonlySet<string> = new Set([
  'phone', 'email', 'address', 'contact', 'name', 'dob', 'ssn',
  'medical_info', 'medicalInfo', 'dateOfBirth',
]);

const DRAFT_ONLY_FIELDS: ReadonlySet<string> = new Set([
  'internal_notes', 'internalNotes',
  'ai_metadata', 'aiMetadata',
  'raw_data', 'rawData',
]);

export const PUBLIC_WHITELIST = new Set<string>([
  'id', 'type', 'title', 'description', 'severity', 'status',
  'geometry', 'startsAt', 'expectedEnd', 'declarationLevel',
  'createdAt', 'updatedAt', 'orgId', 'incidentId',
  'visibility', 'reviewStatus',
]);

export function publicSerialize(
  entity: Record<string, unknown>,
  vis: string,
  reviewStatus: string,
): Record<string, unknown> {
  if (entity === null || entity === undefined) {
    throw new SerializationError('Cannot serialize null or undefined entity');
  }

  if (vis === 'public' && reviewStatus === 'official') {
    const result: Record<string, unknown> = {};
    for (const key of Object.keys(entity)) {
      if (PUBLIC_WHITELIST.has(key)) {
        result[key] = entity[key];
      }
    }
    return result;
  }

  const result: Record<string, unknown> = {};
  for (const key of Object.keys(entity)) {
    if (vis === 'sensitive' && PII_FIELDS.has(key)) continue;
    if (reviewStatus === 'draft' && DRAFT_ONLY_FIELDS.has(key)) continue;
    result[key] = entity[key];
  }
  return result;
}
