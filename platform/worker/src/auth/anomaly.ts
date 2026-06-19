import type { Env } from '../index';
import { drizzle } from 'drizzle-orm/d1';
import { devices } from '../db/schema';
import { eq } from 'drizzle-orm';
import { writeAudit } from '../lib/audit';

export async function checkAnomalousLogin(
  env: Env,
  userId: string,
  deviceFingerprint: string,
  ipRegion: string,
): Promise<{ anomalous: boolean; reason?: string }> {
  const db = drizzle(env.db);

  const knownDevices = await db
    .select()
    .from(devices)
    .where(eq(devices.userId, userId))
    .limit(50)
    .all();

  if (knownDevices.length === 0) return { anomalous: false };

  const knownFingerprint = knownDevices.some((d) => d.fingerprint === deviceFingerprint);
  const knownRegion = knownDevices.some((d) => {
    const parts = d.lastIp?.split('.') ?? [];
    return parts[0] === ipRegion.split('.')[0];
  });

  if (!knownFingerprint && !knownRegion) {
    await writeAudit({
      db,
      orgId: 'system',
      actor: userId,
      action: 'login.anomalous',
      entity: `user:${userId}`,
      after: { deviceFingerprint, ipRegion, reason: 'new_device_and_geo' },
    });
    return { anomalous: true, reason: 'new_device_and_geo' };
  }

  if (!knownFingerprint) {
    await writeAudit({
      db,
      orgId: 'system',
      actor: userId,
      action: 'login.anomalous',
      entity: `user:${userId}`,
      after: { deviceFingerprint, reason: 'new_device' },
    });
    return { anomalous: true, reason: 'new_device' };
  }

  if (!knownRegion) {
    await writeAudit({
      db,
      orgId: 'system',
      actor: userId,
      action: 'login.anomalous',
      entity: `user:${userId}`,
      after: { ipRegion, reason: 'new_geo' },
    });
    return { anomalous: true, reason: 'new_geo' };
  }

  return { anomalous: false };
}
