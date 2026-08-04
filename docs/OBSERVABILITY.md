# Production Observability and SLO Evidence

The backend and dedicated worker emit bounded Prometheus metrics and OpenTelemetry spans. Telemetry is operational evidence, not proof that the production SLO has passed. The production claim requires the declared retention window and an externally operated long-term store.

## SLO source of truth

`config/observability/slos.json` is the normative SLI registry. It declares the formula, denominator, source of truth, window, threshold, burn-rate policy, cardinality limit, retention, and privacy rule for availability, acknowledged-event loss, ingest rate, API-read latency, dashboard latency, saturation, queue age, and dependency health.

The event lifecycle is explicit: `accepted`, `processed`, `failed`, `stale`, and `lost`. An acknowledgement is counted only after the raw event ledger boundary; `lost` is a critical error and is never hidden by a successful API response.

## Trace and privacy contract

The `X-Trace-Id` response header and W3C trace context on queue headers correlate API, queue, worker, model, audit, and client boundaries. Attributes and metric labels are limited to route templates, allowlisted component names, bounded outcomes, model names, dependency names, and queue names. No request bodies, raw event payloads, credentials, access tokens, email addresses, phone numbers, coordinates, tenant identifiers, or unrestricted IDs are emitted.

## Health semantics

`/healthz` is process liveness. It reports dependency reachability as `unknown`, not `configured`, because it performs no dependency probe. `/healthz/deep` probes database, Redis, Redpanda, and MinIO and reports `reachable` or `degraded`; an unknown dependency never counts as healthy. A dependency outage may leave liveness available while readiness and the dependency-health alert are degraded.

## Operator runbook

1. Confirm `up{job="backend"}` and `up{job="worker"}` before interpreting application counters. A missing worker scrape is an incident, not zero worker traffic.
2. Check the event lifecycle dashboard. A rising `accepted` with no `processed` indicates queue backlog; `failed` indicates DLQ/retry pressure; `stale` indicates age policy; `lost` pages immediately.
3. Check `dependency_health`. Do not restart or promote a deployment based on `/healthz` alone when a dependency is `unknown`.
4. For availability burn alerts, compare the 1-hour 14.4x and 6-hour 6x windows, then inspect route-template latency and database query duration. Preserve trace IDs from response headers in the incident record.
5. For queue-age alerts, verify broker reachability, worker process health, retry count, and DLQ acknowledgement. Do not commit offsets for buffered or unacknowledged work.
6. For model alerts, inspect bounded model state (`available`, `abstain`, `unavailable`, `incompatible`) and model latency. Never replace an abstention with a fabricated result.
7. For offline-sync alerts, inspect `offline_sync_total` by status and the durable audit chain. Conflicts and failures require the existing human-resolution policy.
8. Redact tokens, credentials, payloads, PII, and unrestricted identifiers before attaching logs or screenshots to an incident.

Long-term retention, external Alertmanager notification delivery, trace collector availability, key custody, and production evidence capture remain external operational prerequisites until independently recorded.
