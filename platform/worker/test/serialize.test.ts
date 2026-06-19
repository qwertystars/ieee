import { describe, it, expect } from 'vitest';
import { publicSerialize, SerializationError, PUBLIC_WHITELIST } from '../src/lib/serialize';

describe('publicSerialize (FEATURES.md:39)', () => {
  it('strips PII fields from sensitive+draft entity', () => {
    const entity = {
      id: '01HTEST',
      type: 'flood',
      title: 'River overflow',
      name: 'John Doe',
      phone: '555-1234',
      email: 'john@example.com',
      address: '123 Main St',
      internal_notes: 'internal note',
      ai_metadata: { confidence: 0.9 },
      raw_data: { source: 'sensor' },
    };
    const result = publicSerialize(entity, 'sensitive', 'draft');
    expect(result).not.toHaveProperty('name');
    expect(result).not.toHaveProperty('phone');
    expect(result).not.toHaveProperty('email');
    expect(result).not.toHaveProperty('address');
    expect(result).not.toHaveProperty('internal_notes');
    expect(result).not.toHaveProperty('ai_metadata');
    expect(result).not.toHaveProperty('raw_data');
    expect(result).toHaveProperty('id');
    expect(result).toHaveProperty('type');
    expect(result).toHaveProperty('title');
  });

  it('whitelists only public fields when visibility=public and reviewStatus=official', () => {
    const entity = {
      id: '01HTEST',
      type: 'flood',
      title: 'River overflow',
      description: 'Major flooding',
      severity: 'severe',
      status: 'active',
      geometry: '{"type":"Point"}',
      startsAt: 1700000000000,
      expectedEnd: 1700003600000,
      declarationLevel: 'local',
      createdAt: 1700000000000,
      updatedAt: 1700000000000,
      orgId: '01HORG',
      visibility: 'public',
      reviewStatus: 'official',
      internal_notes: 'secret',
      phone: '555-1234',
      raw_data: { source: 'sensor' },
    };
    const result = publicSerialize(entity, 'public', 'official');
    for (const key of Object.keys(result)) {
      expect(PUBLIC_WHITELIST.has(key)).toBe(true);
    }
    expect(result).not.toHaveProperty('internal_notes');
    expect(result).not.toHaveProperty('phone');
    expect(result).not.toHaveProperty('raw_data');
    expect(result).toHaveProperty('id');
    expect(result).toHaveProperty('type');
    expect(result).toHaveProperty('title');
  });

  it('throws SerializationError on null input', () => {
    expect(() =>
      publicSerialize(null as unknown as Record<string, unknown>, 'public', 'official'),
    ).toThrow(SerializationError);
  });

  it('passes through internal+reviewed entity with minimal redaction', () => {
    const entity = {
      id: '01HTEST',
      type: 'flood',
      title: 'River overflow',
      name: 'John Doe',
      phone: '555-1234',
      internal_notes: 'internal note',
      ai_metadata: { confidence: 0.9 },
    };
    const result = publicSerialize(entity, 'internal', 'reviewed');
    expect(result).toHaveProperty('name');
    expect(result).toHaveProperty('phone');
    expect(result).toHaveProperty('internal_notes');
    expect(result).toHaveProperty('ai_metadata');
    expect(result).toHaveProperty('id');
    expect(result).not.toBe(entity);
  });
});
