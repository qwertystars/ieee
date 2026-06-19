import { drizzle } from 'drizzle-orm/d1';
import { idempotency } from '../db/schema';
import { eq, and } from 'drizzle-orm';
import { ulid, nowMs } from './ulid';

type Db = ReturnType<typeof drizzle>;

/**
 * Check if a (source, external_id) pair has already been processed.
 * FEATURES.md:41 — idempotency on external-source rows + queue messages + webhooks.
 *
 * @returns existing result if found, null otherwise
 */
export async function checkIdempotency(
  db: Db,
  source: string,
  externalId: string,
): Promise<unknown | null> {
  const existing = await db
    .select({ result: idempotency.result })
    .from(idempotency)
    .where(and(eq(idempotency.source, source), eq(idempotency.externalId, externalId)))
    .limit(1)
    .all();

  if (existing.length === 0) return null;
  return existing[0]?.result ?? null;
}

/**
 * Record an idempotency result. If (source, external_id) already exists, returns
 * the existing result (no-op, no duplicate).
 */
export async function recordIdempotency(
  db: Db,
  source: string,
  externalId: string,
  result: unknown,
): Promise<unknown> {
  const existing = await checkIdempotency(db, source, externalId);
  if (existing !== null) return existing;

  await db.insert(idempotency).values({
    id: ulid(),
    source,
    externalId,
    result: JSON.stringify(result),
    createdAt: nowMs(),
  });

  return result;
}
