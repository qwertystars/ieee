import { monotonicFactory } from 'ulid';

const ulidFactory = monotonicFactory();

/**
 * Generate a monotonic ULID (26-char Crockford base32).
 * FEATURES.md:38 — all IDs are ULIDs, never UUIDs.
 */
export function ulid(): string {
  return ulidFactory();
}

/**
 * Current UTC time in epoch milliseconds.
 * FEATURES.md:38 — time stored as UTC epoch ms.
 */
export function nowMs(): number {
  return Date.now();
}
