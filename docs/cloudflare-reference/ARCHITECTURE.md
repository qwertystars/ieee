# Cloudflare Workers Production Architecture Reference

This document maps the current PostGIS/FastAPI disaster-response platform to a Cloudflare-native architecture, with production-ready patterns and code samples. All references link to official Cloudflare documentation or official example repositories.

---

## 1. Workers + Hono + chanfana OpenAPI

### Official references
- Chanfana Hono adapter: https://chanfana.pages.dev/router-adapters
- Official chanfana template: https://github.com/cloudflare/templates/tree/main/chanfana-openapi-template

### Production pattern
```typescript
import { ApiException, fromHono } from "chanfana";
import { Hono } from "hono";
import { tasksRouter } from "./endpoints/tasks/router";

const app = new Hono<{ Bindings: Env }>();

app.onError((err, c) => {
  if (err instanceof ApiException) {
    return c.json({ success: false, errors: err.buildResponse() }, err.status);
  }
  console.error(JSON.stringify({ message: "global error", error: String(err), path: c.req.path }));
  return c.json({ success: false, errors: [{ code: 7000, message: "Internal Server Error" }] }, 500);
});

const openapi = fromHono(app, {
  docs_url: "/",
  schema: {
    info: { title: "Disaster Response API", version: "1.0.0", description: "Cloudflare native API" },
  },
});

openapi.route("/tasks", tasksRouter);

export default app;
```

Source: https://github.com/cloudflare/templates/blob/4814875a6f534fb22330c3764e21ba454a068fc8/chanfana-openapi-template/src/index.ts

### Middleware ordering
1. request-id / logger
2. CORS
3. auth / rate-limit
4. chanfana OpenAPI routes
5. error handler registered on root Hono app

---

## 2. Drizzle ORM + D1

### Official references
- Drizzle D1 guide: https://orm.drizzle.team/docs/connect-cloudflare-d1
- D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
- D1 migrations nested layout: https://developers.cloudflare.com/d1/reference/migrations/#nested-migration-layouts

### Production pattern
```typescript
drizzle.config.ts
import { defineConfig } from "drizzle-kit";
export default defineConfig({
  schema: "./src/db/schema.ts",
  out: "./migrations",
  dialect: "sqlite",
  driver: "d1-http",
  dbCredentials: {
    accountId: process.env.CLOUDFLARE_ACCOUNT_ID!,
    databaseId: process.env.CLOUDFLARE_DATABASE_ID!,
    token: process.env.CLOUDFLARE_D1_TOKEN!,
  },
});
```

```typescript
// src/db/schema.ts
import { sqliteTable, text, integer, real } from "drizzle-orm/sqlite-core";
export const observations = sqliteTable("observations", {
  id: text("id").primaryKey(),
  eventId: text("event_id").notNull(),
  observationType: text("observation_type").notNull(),
  lat: real("lat").notNull(),
  lon: real("lon").notNull(),
  timestamp: integer("timestamp", { mode: "timestamp" }).notNull(),
  value: real("value"),
  unit: text("unit"),
  confidence: real("confidence"),
  metadata: text("metadata", { mode: "json" }),
});
```

```typescript
// FTS5 via raw SQL (D1 uses SQLite)
import { sql } from "drizzle-orm";
export async function ensureFts(db: ReturnType<typeof drizzle>) {
  await db.run(sql`
    CREATE VIRTUAL TABLE IF NOT EXISTS incidents_search USING FTS5(
      title, description,
      content=incidents, content_rowid=rowid
    )
  `);
}
```

Nested Drizzle migration example:
https://github.com/cloudflare/templates/blob/4814875a6f534fb22330c3764e21ba454a068fc8/chanfana-openapi-template/wrangler.jsonc

### wrangler.jsonc fragment
```jsonc
{
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "disaster-response",
      "database_id": "<UUID>",
      "migrations_dir": "migrations",
      "migrations_pattern": "migrations/*/migration.sql"
    }
  ]
}
```

---

## 3. Durable Objects: Hibernatable WebSockets, storage, alarms, sharding

### Official references
- Hibernation WebSocket API: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- Durable Object State: https://developers.cloudflare.com/durable-objects/api/state/
- Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- DO fixture: https://github.com/cloudflare/workers-sdk/blob/main/fixtures/vitest-pool-workers-examples/durable-objects/src/index.ts

### Production pattern
```typescript
import { DurableObject } from "cloudflare:workers";

export class IncidentHub extends DurableObject {
  sql: SqlStorage;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    ctx.blockConcurrencyWhile(async () => {
      this.sql.exec(`
        CREATE TABLE IF NOT EXISTS clients (
          websocket_id TEXT PRIMARY KEY,
          role TEXT NOT NULL,
          joined_at INTEGER NOT NULL
        )
      `);
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.headers.get("Upgrade") === "websocket") {
      const [client, server] = Object.values(new WebSocketPair());
      this.ctx.acceptWebSocket(server, [url.searchParams.get("role") ?? "viewer"]);
      this.sql.exec(`INSERT OR REPLACE INTO clients VALUES (?, ?, ?)`,
        crypto.randomUUID(), url.searchParams.get("role") ?? "viewer", Date.now());
      return new Response(null, { status: 101, webSocket: client });
    }
    return new Response("Expected WebSocket", { status: 426 });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer) {
    const data = typeof message === "string" ? message : new TextDecoder().decode(message);
    const payload = JSON.stringify({ type: "broadcast", data });
    for (const conn of this.ctx.getWebSockets()) {
      conn.send(payload);
    }
  }

  async alarm() {
    // batch persistence, heartbeat checks, scheduled alerts
    const next = this.sql.exec<{ next_at: number }>(`SELECT MIN(next_at) FROM scheduled_alerts`).one();
    if (next?.next_at) {
      this.ctx.storage.setAlarm(next.next_at);
    }
  }
}
```

Sharding:
```typescript
const id = env.INCIDENT_HUB.idFromName(`incident:${eventId}`);
const stub = env.INCIDENT_HUB.get(id);
return stub.fetch(request);
```

Recommended: use `acceptWebSocket` not `ws.accept()` so DO hibernates while connections stay alive.

---

## 4. Queues: producers, consumers, DLQ, idempotency

### Official references
- Queues overview: https://developers.cloudflare.com/queues/reference/how-queues-works/
- Batching, retries, delays: https://developers.cloudflare.com/queues/configuration/batching-retries/
- DLQ: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Patterns: https://github.com/cloudflare/skills/blob/main/skills/cloudflare/references/queues/patterns.md

### Producer
```typescript
export default {
  async fetch(request, env, ctx) {
    const payload = await request.json();
    ctx.waitUntil(env.ALERT_QUEUE.send(payload, { contentType: "json" }));
    return Response.json({ status: "queued" }, { status: 202 });
  },
} satisfies ExportedHandler<Env>;
```

### Consumer with DLQ and idempotency
```typescript
export default {
  async queue(batch: MessageBatch<AlertMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        const already = await env.IDEMPOTENCY_KV.get(`processed:${msg.id}`);
        if (already) { msg.ack(); continue; }

        await dispatchAlert(msg.body);

        ctx.waitUntil(env.IDEMPOTENCY_KV.put(`processed:${msg.id}`, "1", { expirationTtl: 86400 }));
        msg.ack();
      } catch (error) {
        console.error(JSON.stringify({ message: "alert failed", id: msg.id, error: String(error) }));
        msg.retry({ delaySeconds: Math.min(30 * (2 ** msg.attempts), 43200) });
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

### wrangler.jsonc fragment
```jsonc
{
  "queues": {
    "producers": [
      { "binding": "ALERT_QUEUE", "queue": "alerts" },
      { "binding": "REPORT_QUEUE", "queue": "reports" },
      { "binding": "NOTIFICATION_QUEUE", "queue": "notifications" }
    ],
    "consumers": [
      {
        "queue": "alerts",
        "max_batch_size": 50,
        "max_batch_timeout": 5,
        "max_retries": 5,
        "dead_letter_queue": "alerts-dlq",
        "retry_delay": 60
      },
      {
        "queue": "alerts-dlq",
        "max_batch_size": 10,
        "max_batch_timeout": 30
      }
    ]
  }
}
```

---

## 5. R2: presigned URLs and range reads for PMTiles

### Official references
- Presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- Workers API range reads: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#ranged-reads
- Skill patterns: https://github.com/cloudflare/skills/blob/main/skills/cloudflare/references/r2/patterns.md

### Presigned upload
```typescript
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const s3 = new S3Client({
  region: "auto",
  endpoint: `https://${env.ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  },
});

const uploadUrl = await getSignedUrl(
  s3,
  new PutObjectCommand({ Bucket: "drp-pmtiles", Key: `${eventId}.pmtiles"`, ContentType: "application/octet-stream" }),
  { expiresIn: 3600 }
);
return Response.json({ uploadUrl });
```

### Range proxy for PMTiles
```typescript
export async function pmtilesRangeProxy(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const key = url.pathname.replace("/tiles/", "");
  const range = request.headers.get("Range");
  const options: R2GetOptions = range ? { range: parseRange(range) } : {};

  const object = await env.PMTILES_BUCKET.get(key, options);
  if (!object) return new Response("Not found", { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);
  if (object.range) {
    headers.set("content-range", `bytes ${object.range.offset}-${object.range.end}/${object.size}`);
  }

  return new Response(object.body, { status: object.range ? 206 : 200, headers });
}
```

---

## 6. Vectorize: index creation, upsert, query

### Official references
- Vectorize API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Create metadata index: https://developers.cloudflare.com/vectorize/reference/client-api/#create-metadata-index
- Patterns: https://github.com/cloudflare/skills/blob/main/skills/cloudflare/references/vectorize/patterns.md

### Index creation
```bash
npx wrangler vectorize create drp-resources-search --dimensions=768 --metric=cosine
npx wrangler vectorize create-metadata-index drp-resources-search --property-name=eventId --type=string
npx wrangler vectorize create-metadata-index drp-resources-search --property-name=category --type=string
```

### Upsert/query pattern
```typescript
// Embed via Workers AI
const emb = await env.AI.run("@cf/baai/bge-base-en-v1.5", { text: [description] });

await env.SEARCH.upsert([{
  id: resourceId,
  values: emb.data[0],
  metadata: { eventId, category, source: "observation" }
}]);

const matches = await env.SEARCH.query(emb.data[0], {
  topK: 10,
  returnMetadata: "indexed",
  filter: { eventId: { $eq: eventId } }
});
```

Tenant isolation:
- < 50K tenants: use `namespace` (fastest)
- > 50K tenants: use indexed metadata `filter`

---

## 7. Workers + Vite + React deployment

### Official references
- React + Vite guide: https://developers.cloudflare.com/workers/framework-guides/web-apps/react/
- Vite tutorial: https://developers.cloudflare.com/workers/vite-plugin/tutorial/
- Vite template: https://github.com/cloudflare/templates/tree/main/vite-react-template

### Recommended structure
```
worker/
  src/
    index.ts
frontend/
  src/
    App.tsx
vite.config.ts
wrangler.jsonc
```

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { cloudflare } from "@cloudflare/vite-plugin";
export default defineConfig({ plugins: [react(), cloudflare()] });
```

```typescript
// worker/src/index.ts
import { Hono } from "hono";
const app = new Hono<{ Bindings: Env }>();
app.get("/api/healthz", (c) => c.json({ status: "ok", version: c.env.API_VERSION }));
export default app;
```

---

## 8. Complete wrangler.jsonc binding example

```jsonc
{
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "disaster-response-cloudflare",
  "main": "worker/src/index.ts",
  "compatibility_date": "2026-06-19",
  "compatibility_flags": ["nodejs_compat"],
  "observability": {
    "enabled": true,
    "logs": { "head_sampling_rate": 1 },
    "traces": { "enabled": true, "head_sampling_rate": 0.01 }
  },
  "upload_source_maps": true,
  "assets": {
    "directory": "./dist/client",
    "not_found_handling": "single-page-application"
  },
  "vars": {
    "API_VERSION": "v1",
    "ENVIRONMENT": "production"
  },
  "d1_databases": [
    { "binding": "DB", "database_name": "disaster-response", "database_id": "<UUID>", "migrations_dir": "migrations", "migrations_pattern": "migrations/*/migration.sql" }
  ],
  "durable_objects": {
    "bindings": [
      { "name": "INCIDENT_HUB", "class_name": "IncidentHub" },
      { "name": "REGION_COORD", "class_name": "RegionCoordinator" }
    ]
  },
  "migrations": [
    { "tag": "v1", "new_sqlite_classes": ["IncidentHub", "RegionCoordinator"] }
  ],
  "kv_namespaces": [
    { "binding": "CACHE", "id": "<UUID>", "preview_id": "<UUID>" },
    { "binding": "IDEMPOTENCY", "id": "<UUID>", "preview_id": "<UUID>" }
  ],
  "r2_buckets": [
    { "binding": "ASSETS", "bucket_name": "drp-assets" },
    { "binding": "PMTILES", "bucket_name": "drp-pmtiles" },
    { "binding": "REPORTS", "bucket_name": "drp-reports" }
  ],
  "queues": {
    "producers": [
      { "binding": "ALERT_QUEUE", "queue": "alerts" },
      { "binding": "REPORT_QUEUE", "queue": "reports" },
      { "binding": "NOTIFICATION_QUEUE", "queue": "notifications" },
      { "binding": "ANALYTICS_QUEUE", "queue": "analytics" }
    ],
    "consumers": [
      {
        "queue": "alerts",
        "max_batch_size": 50,
        "max_batch_timeout": 5,
        "max_retries": 5,
        "dead_letter_queue": "alerts-dlq",
        "retry_delay": 60
      },
      { "queue": "alerts-dlq", "max_batch_size": 10, "max_batch_timeout": 30 },
      { "queue": "reports", "max_batch_size": 10, "max_batch_timeout": 10, "max_retries": 3 }
    ]
  },
  "vectorize": [
    { "binding": "SEARCH", "index_name": "drp-resources-search" }
  ],
  "analytics_engine_datasets": [
    { "binding": "ANALYTICS", "dataset": "drp_metrics" }
  ]
}
```

---

## 9. Testing with @cloudflare/vitest-pool-workers

### Official references
- Vitest integration: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Configuration: https://developers.cloudflare.com/workers/testing/vitest-integration/configuration/
- D1 fixture: https://github.com/cloudflare/workers-sdk/blob/main/fixtures/vitest-pool-workers-examples/d1/vitest.config.ts
- Chanfana template tests: https://github.com/cloudflare/templates/blob/main/chanfana-openapi-template/tests/vitest.config.mts

### vitest.config.mts
```typescript
import path from "node:path";
import { defineWorkersConfig, readD1Migrations } from "@cloudflare/vitest-pool-workers/config";

const migrationsPath = path.join(__dirname, "migrations");
const migrations = await readD1Migrations(migrationsPath);

export default defineWorkersConfig({
  esbuild: { target: "esnext" },
  test: {
    setupFiles: ["./tests/apply-migrations.ts"],
    poolOptions: {
      workers: {
        singleWorker: true,
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          compatibilityFlags: ["experimental", "nodejs_compat"],
          bindings: { MIGRATIONS: migrations }
        }
      }
    }
  }
});
```

### tests/apply-migrations.ts
```typescript
import { applyD1Migrations, env } from "cloudflare:test";
await applyD1Migrations(env.DB, env.MIGRATIONS);
```

### DO test utilities
```typescript
import { runDurableObjectAlarm, runInDurableObject } from "cloudflare:test";
import { env } from "cloudflare:workers";

const id = env.INCIDENT_HUB.newUniqueId();
const stub = env.INCIDENT_HUB.get(id);
await runInDurableObject(stub, (instance: IncidentHub) => {
  instance.scheduleBroadcast(Date.now() + 5000);
});
await runDurableObjectAlarm(stub);
```

---

## 10. Observability

Structured logging from Workers Best Practices:
https://developers.cloudflare.com/workers/best-practices/workers-best-practices/

```typescript
console.log(JSON.stringify({
  message: "incoming request",
  method: request.method,
  path: new URL(request.url).pathname
}));

// Custom metrics
env.ANALYTICS.writeDataPoint({
  blobs: [request.url, request.method, eventId],
  doubles: [response.status, durationMs],
  indexes: [eventId]
});
```

---

## Mapping current domain to Cloudflare primitives

| Current module | Cloudflare primitive |
|----------------|---------------------|
| SQLAlchemy/PostGIS models | Drizzle + D1 |
| Realtime `/ws/events/{event_id}` | Durable Objects Hibernatable WebSockets |
| Worker APScheduler tasks | Queues + DO alarms |
| Report PDF storage | R2 + presigned URLs |
| PMTiles tile serving | R2 byte-range reads |
| Semantic search / RAG | Vectorize + Workers AI embeddings |
| Audit/usage metrics | Analytics Engine / Workers Logs |
| Frontend SPA | Vite + React + Workers Static Assets |

