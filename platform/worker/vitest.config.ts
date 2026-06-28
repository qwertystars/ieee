import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const migrationsDir = path.resolve(__dirname, 'migrations');
const migrationFiles = readdirSync(migrationsDir).filter((f) => f.endsWith('.sql')).sort();
const allSql = migrationFiles
  .map((f) => readFileSync(path.join(migrationsDir, f), 'utf-8'))
  .join('\n')
  .replace(/--> statement-breakpoint/g, ';\n')
  .split(';\n')
  .map((s) => s.trim())
  .filter((s) => s.length > 0);

export default defineWorkersConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    poolOptions: {
      workers: {
        main: './src/index.ts',
        isolatedStorage: false,
        miniflare: {
          d1Databases: ['db'],
          kvNamespaces: ['cache', 'locales'],
          r2Buckets: ['media', 'exports'],
          queues: [
            'ingest', 'ingest-dlq', 'alert', 'alert-dlq', 'ai', 'ai-dlq',
            'drone', 'drone-dlq', 'geocode', 'geocode-dlq',
            'webhook-ingest', 'webhook-ingest-dlq', 'webhook-delivery', 'webhook-delivery-dlq',
          ],
          durableObjects: {
            IncidentRoom: 'IncidentRoom',
            RateLimiter: 'RateLimiter',
            TaskTimer: 'TaskTimer',
            ShelterCounter: 'ShelterCounter',
            AmbulanceQueue: 'AmbulanceQueue',
            AgencyRoom: 'AgencyRoom',
            PasskeyDO: 'PasskeyDO',
          },
          bindings: {
            ENVIRONMENT: 'test',
            __MIGRATION_SQL: JSON.stringify(allSql),
          },
          compatibilityDate: '2024-12-01',
          compatibilityFlags: ['nodejs_compat'],
        },
      },
    },
  },
});
