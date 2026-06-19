import { describe, it, expect } from 'vitest';
import { ulid, nowMs } from '../src/lib/ulid';

describe('ULID helper (FEATURES.md:38)', () => {
  it('generates a 26-character Crockford base32 string', () => {
    const id = ulid();
    expect(id).toHaveLength(26);
    expect(id).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/);
  });

  it('generates monotonically increasing ULIDs within the same millisecond', () => {
    const ids: string[] = [];
    for (let i = 0; i < 100; i++) {
      ids.push(ulid());
    }
    const sorted = [...ids].sort();
    expect(ids).toEqual(sorted);
  });

  it('generates unique ULIDs', () => {
    const ids = new Set<string>();
    for (let i = 0; i < 1000; i++) {
      ids.add(ulid());
    }
    expect(ids.size).toBe(1000);
  });
});

describe('nowMs helper (FEATURES.md:38)', () => {
  it('returns a positive integer (UTC epoch ms)', () => {
    const ts = nowMs();
    expect(typeof ts).toBe('number');
    expect(Number.isInteger(ts)).toBe(true);
    expect(ts).toBeGreaterThan(0);
    expect(ts).toBeGreaterThan(1700000000000);
  });
});
