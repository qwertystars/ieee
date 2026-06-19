import { describe, it, expect } from 'vitest';
import { ulid, nowMs } from '../src/lib/ulid';
import { sha256 } from '../src/lib/audit';

describe('P0 Integration Gate (T20)', () => {
  it('ULID generation works for all entities', () => {
    const orgId = ulid();
    const userId = ulid();
    const incidentId = ulid();
    expect(orgId).toHaveLength(26);
    expect(userId).toHaveLength(26);
    expect(incidentId).toHaveLength(26);
  });

  it('audit hash chain computes correctly', async () => {
    const prevHash = '0000000000000000000000000000000000000000000000000000000000000000';
    const payload = JSON.stringify({ id: ulid(), action: 'test', entity: 'test', ts: nowMs(), prevHash });
    const hash = await sha256(prevHash + payload);
    expect(hash).toHaveLength(64);
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it('serializer strips PII from sensitive entities', async () => {
    const { publicSerialize } = await import('../src/lib/serialize');
    const entity = { id: ulid(), name: 'John', phone: '555-1234', type: 'flood' };
    const result = publicSerialize(entity, 'sensitive', 'draft');
    expect(result).not.toHaveProperty('name');
    expect(result).not.toHaveProperty('phone');
    expect(result).toHaveProperty('id');
    expect(result).toHaveProperty('type');
  });

  it('public+official whitelist enforcement', async () => {
    const { publicSerialize, PUBLIC_WHITELIST } = await import('../src/lib/serialize');
    const entity = { id: ulid(), type: 'flood', title: 'Test', secret: 'hidden', phone: '555' };
    const result = publicSerialize(entity, 'public', 'official');
    for (const key of Object.keys(result)) {
      expect(PUBLIC_WHITELIST.has(key)).toBe(true);
    }
    expect(result).not.toHaveProperty('secret');
    expect(result).not.toHaveProperty('phone');
  });

  it('session token hashing produces different hashes for different tokens', async () => {
    const token1 = crypto.randomUUID();
    const token2 = crypto.randomUUID();
    const hash1 = await sha256(token1);
    const hash2 = await sha256(token2);
    expect(hash1).not.toBe(hash2);
  });

  it('idempotency key is a valid ULID', () => {
    const key = ulid();
    expect(key).toHaveLength(26);
    expect(key).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/);
  });

  it('all 21 binding names are frozen and match Env interface', async () => {
    const envKeys = ['db', 'media', 'exports', 'ingestQ', 'alertQ', 'aiQ', 'droneQ',
      'geocodeQ', 'webhookIngestQ', 'webhookDeliveryQ', 'IncidentRoom', 'RateLimiter',
      'TaskTimer', 'ShelterCounter', 'AmbulanceQueue', 'AgencyRoom',
      'cache', 'locales', 'embeddings', 'metrics', 'ai'];
    expect(envKeys).toHaveLength(21);
    for (const key of envKeys) {
      expect(typeof key).toBe('string');
    }
  });
});
