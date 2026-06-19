import { describe, it, expect } from 'vitest';
import { sha256 } from '../src/lib/audit';

describe('sha256 helper', () => {
  it('produces a 64-character hex string', async () => {
    const hash = await sha256('test');
    expect(hash).toHaveLength(64);
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it('produces the known SHA-256 of "test"', async () => {
    const hash = await sha256('test');
    expect(hash).toBe('9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08');
  });

  it('produces different hashes for different inputs', async () => {
    const hash1 = await sha256('input1');
    const hash2 = await sha256('input2');
    expect(hash1).not.toBe(hash2);
  });
});
