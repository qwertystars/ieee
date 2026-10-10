# Disaster Response Command SaaS — Feature List v2 (Build-Annotated)

Superset of v1. Every section now has a `> Build:` block (architecture + keywords) and selected features carry inline hints in backticks. Format is designed so a coding agent can pick the next unchecked box, read the section's Build block, and implement it end-to-end.

---

## Agent Protocol (read first)

1. Work in **Build Phase order** (below). Within a section, top-to-bottom unless `Deps:` says otherwise.
2. Before any feature: read the section's `> Build:` block. It defines the shared schema/infra for the whole section — don't reinvent per feature.
3. One feature = one unit of work: Drizzle migration (if schema delta) → API route(s) → UI → test → mark `[x]` → commit `feat(section): feature-name`.
4. Never violate the Conventions below (tenancy, visibility, idempotency). These are global invariants, not per-feature choices.
5. External provider needed (SMS, weather key, etc.)? Code against a thin adapter interface, read config from env/`integrations` table, add to `.env.example`, stub in dev, move on.
6. Any webhook / queue consumer / cron path must be idempotent (unique key + upsert or dedupe table).
7. AI-generated artifacts always land as `status=draft` and require human approval before becoming official/public.
8. If a feature is ambiguous, implement the smallest version that satisfies the line, leave a `<!-- TODO -->` note under it, keep moving.

## Recommended Stack (default; swap if needed)

- **Edge/API:** Cloudflare Workers + Hono + TypeScript. OpenAPI via `chanfana`.
- **DB:** D1 + Drizzle ORM. Full-text via SQLite **FTS5**. Optional per-tenant D1 database pattern for big orgs.
- **Live state:** Durable Objects — one `IncidentRoom` DO per incident (WebSocket fanout, presence, live panels, geofence checks, atomic counters). Token-bucket DOs for rate limits.
- **Async:** Cloudflare Queues (+ DLQ, idempotency keys), Workflows (durable multi-step: alert fanout, report gen, sims), Cron Triggers (feed pulls, retention, backups), DO alarms (per-task SLA timers).
- **Files:** R2 (or B2) via presigned upload URLs; serve through Worker. Rasters as **COG** (cloud-optimized GeoTIFF) on R2.
- **Vectors:** Cloudflare Vectorize + BYO embeddings (or Workers AI `@cf/baai/bge-m3` as zero-key fallback).
- **Geo (critical — D1 has no PostGIS):** geometry stored as GeoJSON TEXT; spatial index = **H3** (`h3-js`, res 8–10) rows in `geo_index(entity_type, entity_id, h3)`; query = polygon → H3 cover → SQL join → `turf.js` refine. Routing = OSM graph in D1 + Dijkstra/A* in Worker for city scale; `Valhalla`/`OSRM`/`openrouteservice` for large.
- **Maps:** MapLibre GL JS; basemap = Protomaps **PMTiles** on R2 (Worker range reads); drawing = `terra-draw`; heavy viz = `deck.gl`; 3D = CesiumJS (sci-fi tier).
- **Frontend:** React + Vite on Pages, Tailwind, TanStack Query/Router, ECharts, PWA via Workbox.
- **Auth:** Clerk (or `better-auth`) + WebAuthn passkeys; SSO/SAML via WorkOS keyword.
- **AI:** BYO OpenAI-compatible endpoint (baseUrl + key + model), JSON mode + zod validation, fallback chain, Workers AI as no-key fallback.
- **Comms:** MSG91/Twilio (SMS + voice/TTS), WhatsApp Cloud API, Resend/SES email, FCM + Web Push (VAPID), Telegram Bot API. Alert interop = **CAP v1.2** (SACHET India / IPAWS US keywords).
- **Heavy compute (sims, OCR, orthomosaics):** Cloudflare Containers or external job runner fed by Queues; results back to R2/D1.
- **PDF/exports:** Cloudflare Browser Rendering (print CSS → PDF), `pdf-lib` for form-fill, `docx` npm, `papaparse` CSV.

## Conventions (global invariants)

- **Tenancy:** every table has `org_id`; incident-scoped tables also `incident_id`. Enforced by middleware, never trusted from client.
- **IDs:** ULIDs. **Time:** UTC epoch ms, render in incident-local TZ.
- **Visibility:** shareable entities carry `visibility ∈ {public, internal, sensitive}` + `review_status ∈ {draft, reviewed, official}`. Public serializers whitelist fields; redaction lives in one serializer layer, not scattered.
- **Audit:** append-only `events(actor, action, entity, before, after, ts, prev_hash, hash)` — hash-chained (sha256(prev_hash‖payload)) for tamper evidence.
- **Idempotency:** external-source rows unique on `(source, external_id)`; queue messages carry idempotency keys; webhook ingest = HMAC-verified + delivery-id dedupe.
- **Forms:** dynamic forms are JSON-Schema docs rendered by one Form Builder engine; don't hand-build per-form UIs.
- **AI:** all calls logged (prompt version, tokens, latency, cost); untrusted data fenced in delimited blocks (prompt-injection firewall); outputs zod-validated with one retry-on-parse-fail.

## Build Phases (dependency order)

- **P0** Core Platform (auth, orgs, RBAC, settings, audit, API skeleton)
- **P1** Incident Creation + `IncidentRoom` DO + Command Center skeleton
- **P2** Map System
- **P3** Emergency Tasks + Field Responder PWA + Requests For Help
- **P4** Shelters + Missing Persons + Population Impact
- **P5** Data Ingestion + Weather + feed Integrations
- **P6** Communications + Public Portal
- **P7** AI Configuration + copilots + Reports
- **P8** Evacuation + Medical + Logistics + Infrastructure
- **P9** Prediction/Simulation + Drone + Damage Assessment
- **P10** Analytics + Decision Support + Search/KB
- **P11** Security hardening + Compliance + Admin + Developer Platform + Offline
- **P12** Multi-Agency + Drills + Early Warning + Recovery + Finance
- **P13** Observability/QA + Deployment + Accessibility/Localization (start at P0, finish here)
- **P14** Sci-Fi backlog

---

## Core Platform
> **Build:** Hono route groups per role-dashboard over shared components. Tables: `orgs, users, memberships(role), roles, role_permissions, settings(scope, key, json), api_keys, sessions, devices`. RBAC = policy middleware `can(actor, action, subject)` (CASL-style); custom roles = rows, not code. Status pages = public Worker route + KV cache. Rate limits = token-bucket DO per org/key. Offline/low-bandwidth → see Offline section.
> **Deps:** none (P0).

- [x] Multi-tenant disaster response SaaS — `org_id everywhere; per-tenant D1 optional`
- [x] Organization workspaces
- [x] Agency workspaces
- [x] Incident workspaces
- [x] Role-based access control — `policy middleware, CASL-style`
- [x] Permission groups
- [x] Custom roles — `role/permission rows, editable UI`
- [x] Admin dashboard
- [x] Operator dashboard
- [x] Field responder dashboard
- [x] Public information dashboard
- [x] Volunteer dashboard
- [x] Shelter manager dashboard
- [x] Medical team dashboard
- [x] Logistics team dashboard
- [x] Command center dashboard
- [x] Liaison officer dashboard
- [x] Donor / partner read-only dashboard
- [x] Multi-region deployment support — `CF global by default; Smart Placement keyword`
- [x] Multi-language interface — `i18next + ICU messages`
- [x] Mobile-first responsive UI
- [x] Dark mode
- [x] Offline-first field mode — `see Offline section`
- [x] Low-bandwidth mode — `no map tiles, text lists, tiny payloads`
- [x] Printable reports — `print CSS + Browser Rendering`
- [x] Exportable incident packets
- [x] Full audit trail — `hash-chained events table`
- [x] Activity timeline
- [x] Incident history archive
- [x] Secure session management
- [x] Device login tracking
- [x] Emergency lockout mode — `org-wide kill switch, sessions revoked`
- [x] Workspace-level settings
- [x] Incident-level settings
- [x] Configurable severity levels — `seeded config table, tenant overrides`
- [x] Configurable disaster types
- [x] Configurable response workflows
- [x] Configurable status labels
- [x] Configurable map layers
- [x] Configurable alert templates
- [x] Custom agency branding — `logo/colors in settings, CSS vars`
- [x] Public status page
- [x] Internal status page
- [x] API-only mode
- [x] Webhook-first architecture
- [x] Full REST API — `same Hono routes, key auth`
- [x] OpenAPI documentation — `chanfana`
- [x] API key management — `hashed keys + prefix lookup, scopes`
- [x] Service account support
- [x] Rate limits per organization — `token-bucket DO`
- [x] Usage analytics — `Workers Analytics Engine`
- [x] System health dashboard
- [x] Org switcher
- [x] Invite links with preset role
- [x] Email-domain auto-join allowlist
- [x] Read-only observer role
- [x] Global notification center / in-app inbox
- [x] Command palette — `cmdk`
- [x] Keyboard shortcuts
- [x] Timezone-aware rendering — `incident-local TZ`
- [x] Metric/imperial unit toggle
- [x] Guided onboarding tour
- [x] Demo sandbox org with seeded incident
- [x] Scheduled full-org data export — `cron → R2 zip`
- [x] Data residency region pin — `jurisdiction note per tenant`

## Incident Creation
> **Build:** `incidents(org_id, type, severity, status, escalation, title, desc, geometry GeoJSON, starts_at, expected_end, config json)` + `geo_index` H3 cover rows. Types/severities seeded + tenant-overridable. On create: instantiate `IncidentRoom` DO (`idFromName(incidentId)`), seed default map layers, response checklist, operational period #1, draft public alert. Auto-* features = AI calls (AI section) producing drafts.
> **Deps:** Core Platform.

- [x] Create wildfire incident
- [x] Create flood incident
- [x] Create cyclone incident
- [x] Create earthquake incident
- [x] Create landslide incident
- [x] Create chemical spill incident
- [x] Create heatwave incident
- [x] Create power outage incident
- [x] Create civil emergency incident
- [x] Create disease outbreak incident
- [x] Create tsunami incident
- [x] Create tornado incident
- [x] Create avalanche incident
- [x] Create drought incident
- [x] Create building collapse incident
- [x] Create crowd-crush / stampede incident
- [x] Create industrial fire incident
- [x] Create oil spill incident
- [x] Create radiological incident
- [x] Create multi-hazard "complex" incident — `parent with linked sub-incidents`
- [x] Create custom disaster incident
- [x] Incident title
- [x] Incident description
- [x] Incident type
- [x] Incident severity
- [x] Incident location
- [x] Incident boundary drawing — `terra-draw → GeoJSON`
- [x] Incident start time
- [x] Incident expected duration
- [x] Incident affected radius — `turf.buffer`
- [x] Incident command owner
- [x] Incident response teams
- [x] Incident attachments — `R2 presigned`
- [x] Incident notes
- [x] Incident source links
- [x] Incident tags
- [x] Incident status
- [x] Incident escalation level
- [x] Incident declaration level — `watch / warning / declared enum`
- [x] Sub-incidents
- [x] Incident linking
- [x] Incident merge — `move children + tombstone redirect`
- [x] Incident split
- [x] Clone previous incident
- [x] Incident from template
- [x] Import incident from file — `zod-validated JSON/CSV`
- [x] Import incident from API
- [x] Feed-triggered auto-draft incident — `e.g. USGS quake > M5 in AOI → draft`
- [x] Auto-generate incident summary
- [x] Auto-create response checklist
- [x] Auto-create first operational period
- [x] Auto-create default map layers
- [x] Auto-create public alert draft
- [x] Auto-draft ICS-201 incident briefing — `ICS form mapping, see Reports`

## Command Center
> **Build:** Panels = React components reading `GET /incidents/:id/summary` (D1 aggregates) + live `{panel, delta}` patches over `IncidentRoom` DO WebSocket. Presence/cursors = DO broadcast of `{userId, pos}`. Shared annotations = Yjs doc persisted in DO storage. Layer trust states = `visibility` + `review_status` enums (Conventions). IAP/sitrep = AI draft → human edit → approve (Reports section). ICS keywords: 201 briefing, 202 objectives, 203 org, 204 assignments, 205 comms plan, 206 medical plan, 209 status, 211 check-in, 214 unit log.
> **Deps:** Incident Creation; live overlays need Map System.

- [x] Live operational dashboard
- [x] Incident overview panel
- [x] Current threat panel
- [x] Population impact panel — `reads Population Impact aggregates`
- [x] Evacuation panel
- [x] Shelter panel
- [x] Resource panel
- [x] Field team panel
- [x] Weather panel
- [x] Infrastructure panel
- [x] Communications panel
- [x] Road access panel
- [x] Medical needs panel
- [x] Timeline panel
- [x] Open task panel
- [x] Critical alerts panel
- [x] Decision log panel
- [x] Map-first command view
- [x] Table-first command view
- [x] Kanban response board — `dnd-kit`
- [x] Priority queue
- [x] Situation report generator
- [x] Operational period planning
- [x] Incident action plan builder — `ICS-202/204 composition`
- [x] Commander approval flow
- [x] Escalation workflow
- [x] Shift handoff notes
- [x] Briefing mode — `fullscreen, big type, auto-cycle panels`
- [x] War-room screen mode
- [x] TV display mode — `unauthenticated signed-URL kiosk route`
- [x] Real-time collaboration
- [x] Multi-user cursor presence — `DO broadcast`
- [x] Shared annotations — `Yjs in DO storage`
- [x] Locked official data layers
- [x] Draft data layers
- [x] Reviewed data layers
- [x] Public-safe data layers
- [x] Sensitive data layers
- [x] ICS organization chart builder — `ICS-203/207`
- [x] Objectives tracker — `ICS-202`
- [x] Resource status T-card board — `T-cards keyword`
- [x] Communications plan builder — `ICS-205, radio channels`
- [x] Medical plan builder — `ICS-206`
- [x] Personnel check-in list — `ICS-211`
- [x] Unit activity log — `ICS-214, feeds Finance time capture`
- [x] Briefing/meeting scheduler — `planning P cycle keyword`
- [x] Pinned command priorities strip
- [x] Cross-incident regional overview — `org-level rollup`

## Map System
> **Build:** MapLibre GL JS; basemap = Protomaps PMTiles on R2 served via Worker range reads (`pmtiles` js protocol). Drawing = terra-draw → GeoJSON zones with `zone_type` enum (one engine, all "Draw X" lines). Geometry ops = turf.js; spatial index = h3-js in `geo_index`. `map_layers(incident_id, name, kind, source(geojson|tile|wms), style json, visibility, review_status, sort, version)`. Static overlays = imported datasets (Overture/OSM extracts, gov shapefiles via `shpjs`); live overlays = DO WebSocket sources. Exports = Cloudflare Browser Rendering screenshot/PDF. Public map = separate route, public-visibility layers only.
> **Deps:** Core Platform, Incident Creation.

- [x] Interactive disaster map — `maplibre-gl`
- [x] Satellite map layer — `ESRI World Imagery / Sentinel-2 cloudless keywords`
- [x] Street map layer — `Protomaps PMTiles`
- [x] Terrain map layer — `terrain-RGB tiles`
- [x] Dark map layer
- [x] Offline map tiles — `PMTiles region packs, see Offline`
- [x] Custom tile provider support — `XYZ/WMS URL in layer config`
- [x] Draw polygon zones — `terra-draw; all draw features = zone_type enum`
- [x] Draw evacuation areas
- [x] Draw shelter catchment areas
- [x] Draw road closure areas
- [x] Draw danger zones
- [x] Draw safe zones
- [x] Draw search zones
- [x] Draw responder staging zones
- [x] Draw medical triage zones
- [x] Draw no-entry zones
- [x] Draw supply drop zones
- [x] Draw drone survey zones
- [x] Draw predicted spread zones
- [x] Layer opacity control
- [x] Layer ordering
- [x] Layer grouping
- [x] Layer permissions
- [x] Layer version history — `layer_versions table, diff = geojson compare`
- [x] Layer comparison — `side-by-side or swipe`
- [x] Time slider for map changes — `versioned snapshots by ts`
- [x] Heatmap visualization — `maplibre heatmap layer / deck.gl`
- [x] Population density overlay — `Kontur H3 hexes`
- [x] Building footprint overlay — `Overture / MS Building Footprints`
- [x] Road network overlay — `OSM extract`
- [x] Hospital overlay — `OSM/Overture POI import`
- [x] School overlay
- [x] Shelter overlay
- [x] Police station overlay
- [x] Fire station overlay
- [x] Cell tower overlay — `OpenCelliD keyword`
- [x] Power grid overlay
- [x] Water supply overlay
- [x] Railway overlay
- [x] Bridge overlay
- [x] Floodplain overlay
- [x] Elevation overlay — `Copernicus GLO-30 DEM, hillshade`
- [x] Wind direction overlay — `particle/arrow layer from Open-Meteo grid`
- [x] Rainfall overlay
- [x] Temperature overlay
- [x] Air quality overlay — `OpenAQ`
- [x] Hazard plume overlay — `Gaussian plume output, see Prediction`
- [x] Live responder location overlay — `DO WebSocket`
- [x] Live vehicle location overlay
- [x] Live drone location overlay
- [x] Live request-for-help overlay
- [x] Live shelter capacity overlay
- [x] Live hospital capacity overlay
- [x] Marker clustering — `supercluster`
- [x] Isochrone overlay — `openrouteservice isochrones`
- [x] 3D terrain view — `maplibre terrain`
- [x] Geofence alert zones — `zone + rule → DO checks`
- [x] Geotagged photos on map — `EXIF GPS pins`
- [x] USNG/MGRS grid overlay — `mgrs npm`
- [x] Map search
- [x] Coordinate search — `lat-lng, MGRS, what3words API`
- [x] Address search — `Nominatim/Photon geocoder`
- [x] Reverse geocoding
- [x] Distance measurement — `turf.length`
- [x] Area measurement — `turf.area`
- [x] Route measurement
- [x] Saved measurement annotations
- [x] Legend builder
- [x] Print layout composer — `title block, scale bar, north arrow`
- [x] Map screenshot export — `Browser Rendering`
- [x] Map PDF export
- [x] Public-safe map export
- [x] Embeddable public map — `iframe, public layers only`

## Data Ingestion
> **Build:** Everything lands in one staging table `raw_reports(source, external_id UNIQUE-with-source, payload json, geo, observed_at, confidence, status)` via Queues; validate (zod) → human-verify queue (optional per source) → promote to typed tables. Pull feeds = Cron Triggers; push = HMAC-verified webhooks. Geocode = Nominatim/Photon (self-host keyword) + cache table. OCR = Workers AI vision or Tesseract-in-Container. EXIF = `exifr`. Dedupe = unique keys + simhash / embedding cosine (Vectorize). Inbound email = Cloudflare Email Workers.
> **Deps:** Core Platform; verification UI needs Command Center.

- [x] Manual data entry
- [x] CSV upload — `papaparse`
- [x] Excel upload — `SheetJS`
- [x] GeoJSON upload
- [x] KML upload — `togeojson`
- [x] Shapefile upload — `shpjs`
- [x] GPX upload
- [x] PDF report upload — `text extract in container`
- [x] Image upload
- [x] Drone image upload
- [x] Sensor feed import — `generic webhook adapter`
- [x] Weather feed import — `Open-Meteo cron`
- [x] Seismic feed import — `USGS GeoJSON feed`
- [x] River gauge feed import — `USGS NWIS / CWC India-WRIS`
- [x] Fire detection feed import — `NASA FIRMS VIIRS/MODIS API`
- [x] Satellite detection feed import — `GDACS, Copernicus EMS`
- [x] Road closure feed import
- [x] Emergency call feed import
- [x] Shelter registry import
- [x] Hospital registry import
- [x] Volunteer registry import
- [x] Asset inventory import
- [x] Building database import — `Overture / MS footprints`
- [x] Census data import
- [x] Population grid import — `Kontur H3 / WorldPop`
- [x] Power outage feed import
- [x] Cell outage feed import
- [x] Radio outage feed import
- [x] Social media report import
- [x] Public report form import
- [x] SMS report import — `Twilio/MSG91 inbound webhook`
- [x] WhatsApp report import — `WhatsApp Cloud API webhook`
- [x] Email report import — `CF Email Workers`
- [x] Telegram report import — `Telegram Bot API`
- [x] IVR hotline report import — `Twilio/Exotel voice keypad + transcript`
- [x] RSS/Atom feed import
- [x] CAP alert feed import — `CAP v1.2 XML parse; SACHET/IPAWS`
- [x] Webhook data import
- [x] API data import
- [x] Scheduled data sync — `Cron Triggers`
- [x] Manual sync trigger
- [x] Ingest mapping templates — `saved column→field maps per source`
- [x] Quarantine queue for failed validation
- [x] Schema drift alerts
- [x] Duplicate detection
- [x] Embedding-based near-duplicate detection — `Vectorize cosine`
- [x] Data validation — `zod`
- [x] Data confidence scoring
- [x] Source reliability scoring — `rolling accuracy per source`
- [x] Human verification workflow
- [x] Conflicting report detection — `same geo+time window, different values`
- [x] Data normalization
- [x] Data enrichment
- [x] Language detection on ingest — `franc / AI`
- [x] Machine translation on ingest — `AI translate, keep original`
- [x] Image moderation gate — `vision model NSFW/gore check`
- [x] Geocoding pipeline
- [x] Reverse geocoding pipeline
- [x] Bulk geocode job — `Queue batch`
- [x] Attachment metadata extraction
- [x] OCR for uploaded documents — `Workers AI vision / Tesseract container`
- [x] Image metadata extraction
- [x] EXIF location extraction — `exifr`
- [x] Timestamp normalization
- [x] Source provenance tracking
- [x] Replayable ingest log — `re-run promotion from raw_reports`

## AI Configuration
> **Build:** Provider config `{baseUrl, apiKey, model, headers, endpointPath}` resolved user → incident → org. One call wrapper: OpenAI-compatible `chat.completions`, JSON mode, zod schema parse with 1 retry (feed parse error back), AbortController timeout, fallback model → fallback provider chain. Log every call (`ai_calls`: prompt name+version, tokens, latency, est cost) → D1 + Analytics Engine. Prompts = `prompts(name, version, body with {{vars}}, schema)` table, not code. All generation features below = a prompt template + a zod schema + a draft-status artifact. Injection defense: untrusted data fenced + instruction firewall preamble; PII mask pass (regex + NER prompt) before send when `safe mode` on. Workers AI = zero-key fallback (`@cf/meta/llama-3.1`, embeddings `@cf/baai/bge-m3`).
> **Deps:** Core Platform; consumers everywhere.

- [x] Bring-your-own AI provider
- [x] OpenAI-compatible base URL input
- [x] OpenAI-compatible API key input — `encrypted at rest, Secrets-wrapped`
- [x] Model name input
- [x] Custom request headers
- [x] Custom endpoint path
- [x] Provider connection test — `1-token ping`
- [x] Model availability test
- [x] Embeddings provider config — `for Vectorize/RAG`
- [x] Vision model config — `for damage/drone/OCR features`
- [x] Workers AI zero-key fallback
- [x] Prompt-only AI architecture
- [x] No model training required
- [x] No fine-tuning required
- [x] Organization-level AI settings
- [x] Incident-level AI settings
- [x] User-level AI settings
- [x] AI disabled mode
- [x] AI safe mode — `masking on, approval mandatory`
- [x] AI cost control — `per-tenant spend caps`
- [x] AI token usage tracking
- [x] AI request logging
- [x] AI response logging
- [x] AI prompt versioning
- [x] AI prompt templates
- [x] AI prompt library
- [x] AI prompt variables
- [x] AI prompt preview — `render with sample data`
- [x] AI prompt A/B comparison
- [x] AI output schema validation — `zod`
- [x] AI retry logic
- [x] AI fallback model
- [x] AI provider fallback
- [x] AI timeout settings
- [x] AI max token settings
- [x] AI temperature settings
- [x] AI reasoning effort setting
- [x] AI streaming responses — `SSE passthrough`
- [x] AI batch generation queue
- [x] AI structured JSON outputs
- [x] AI citation requirement — `must cite data row ids; validate they exist`
- [x] AI confidence score
- [x] AI uncertainty flag
- [x] AI hallucination warning
- [x] AI human approval gate — `draft → approve, global convention`
- [x] AI red-team test mode
- [x] AI jailbreak/injection test suite — `golden attack set in CI`
- [x] AI eval harness with golden set — `fixture inputs → expected schema/quality`
- [x] AI audit replay
- [x] AI answer comparison
- [x] AI output diff viewer
- [x] AI latency tracking
- [x] AI prompt injection detection
- [x] AI sensitive data masking
- [x] AI public-safe rewriting
- [x] AI incident summary generation
- [x] AI report generation
- [x] AI task generation
- [x] AI evacuation recommendation generation
- [x] AI shelter recommendation generation
- [x] AI responder prioritization generation
- [x] AI weather impact explanation
- [x] AI logistics explanation
- [x] AI public alert drafting
- [x] AI multilingual translation — `translate + human review queue`
- [x] AI command briefing generation
- [x] AI radio message drafting — `brevity codes, char limits`
- [x] AI SMS message drafting — `160-char aware`
- [x] AI email message drafting
- [x] AI social post drafting
- [x] AI missing-data question generation
- [x] AI operator copilot — `chat over incident state, tool-calling allowlist`
- [x] AI field responder copilot
- [x] AI public information officer copilot
- [x] AI logistics copilot
- [x] AI shelter manager copilot
- [x] AI medical triage copilot
- [x] AI policy compliance checker
- [x] AI risk explanation engine
- [x] AI timeline reconstruction
- [x] AI anomaly detection using prompt analysis
- [x] AI data quality explanation
- [x] AI source conflict explanation
- [x] AI decision memo writer
- [x] AI after-action report writer
- [x] RAG corpus selection per copilot — `Vectorize namespaces`
- [x] Tool-calling allowlist per copilot — `read-only tools by default`

## Population Impact Analysis
> **Build:** Preload Kontur Population dataset (H3 res 8, on HDX) for served regions → `pop_h3(h3, pop)` (batch load R2 → D1). Any zone estimate = polygon → H3 cover → `SUM(pop)`. Alternates: WorldPop, GHSL, Meta HRSL; day/night = LandScan keyword. Demographic splits = census ratio config per admin area. Facility counts = Overture/OSM POI joins. Confidence = dataset resolution + age heuristic; manual override row wins but both kept.
> **Deps:** Map System, Data Ingestion (census/pop imports).

- [x] Estimate affected population — `H3 cover → SUM`
- [x] Estimate population by zone
- [x] Estimate population by radius — `turf.buffer → cover`
- [x] Estimate vulnerable population — `census ratios`
- [x] Estimate elderly population
- [x] Estimate children population
- [x] Estimate disabled population
- [x] Estimate hospital patients affected — `facility capacity × in-zone`
- [x] Estimate school students affected
- [x] Estimate tourists affected
- [x] Estimate workers affected — `day-population, LandScan keyword`
- [x] Estimate households affected — `pop / avg household size`
- [x] Estimate buildings affected — `footprints in zone`
- [x] Estimate critical facilities affected
- [x] Day vs night population toggle
- [x] Informal settlement flag — `manual layer, higher vulnerability weight`
- [x] Livestock estimate — `rural; agri census config`
- [x] Languages-spoken estimate — `census ratios → alert language mix`
- [x] Population impact heatmap — `H3 hex layer`
- [x] Population impact by administrative area
- [x] Population impact by ward
- [x] Population impact by district
- [x] Population impact by census block
- [x] Population impact trend over time — `zone version snapshots`
- [x] People needing evacuation estimate
- [x] People needing shelter estimate — `evac × shelter-seeking ratio config`
- [x] People needing medical help estimate
- [x] People needing food estimate
- [x] People needing water estimate — `Sphere standards keyword (15L/person/day)`
- [x] People trapped estimate
- [x] People unreachable estimate
- [x] Confidence score for population estimate
- [x] Manual override for population estimate
- [x] Data source comparison for population estimate
- [x] Building-level population estimate — `footprint area × floors heuristic`
- [x] Export population impact report

## Evacuation Management
> **Build:** Road graph = OSM extract → `edges(nodes, length, capacity, oneway)` in D1 per region (offline job). Routing = Dijkstra/A* in Worker for city scale; Valhalla/OSRM/openrouteservice for large. Hazard-aware = edge weight penalty/∞ when edge H3 intersects hazard layer. Contraflow = reversed-direction capacity flag. Congestion = demand/capacity (BPR function keyword). Duration = queueing model: zone pop × vehicle occupancy vs route capacity over time steps. Zone lifecycle = `advisory → ordered → in-progress → cleared`. Compliance = household status rows from door-to-door tasks + shelter check-ins. Heavy sims → Prediction section.
> **Deps:** Map System, Population Impact, Tasks.

- [x] Recommend evacuation zones — `hazard layer + buffer + pop`
- [x] Recommend phased evacuation order — `nearest-risk-first batching`
- [x] Recommend evacuation start time
- [x] Recommend evacuation priority
- [x] Recommend evacuation routes
- [x] Recommend alternate routes — `k-shortest paths`
- [x] Recommend no-go routes
- [x] Recommend contraflow routes
- [x] Estimate evacuation duration
- [x] Estimate route congestion — `BPR`
- [x] Estimate vehicle demand
- [x] Estimate bus demand — `carless pop ratio config`
- [x] Estimate ambulance demand
- [x] Estimate accessible transport demand
- [x] Route capacity analysis
- [x] Road closure aware routing
- [x] Flood-aware routing
- [x] Fire spread aware routing
- [x] Wind-aware routing
- [x] Bridge failure aware routing
- [x] Traffic signal disruption aware routing
- [x] Public transit disruption aware routing
- [x] Evacuation staging points
- [x] Evacuation pickup points
- [x] Evacuation assembly areas
- [x] Evacuation route map export
- [x] Evacuation order builder
- [x] Evacuation alert templates
- [x] Evacuation zone status board — `advisory/ordered/cleared`
- [x] Evacuation compliance tracker
- [x] Evacuation completion tracker
- [x] Evacuation refusal tracker
- [x] Door-to-door evacuation tasking — `task batch per street segment`
- [x] Household evacuation status
- [x] Animal evacuation support
- [x] Hospital evacuation support
- [x] School evacuation support
- [x] Prison evacuation support
- [x] Industrial facility evacuation support
- [x] Fuel availability along routes — `station status layer`
- [x] Multilingual evacuation order export
- [x] Evacuation simulation — `see Prediction`
- [x] Evacuation scenario comparison
- [x] Evacuation bottleneck detector — `max demand/capacity edges`
- [x] Reverse evacuation warning
- [x] Re-entry planning
- [x] Re-entry permit workflow — `QR permits, scan validation`
- [x] Safe return notification

## Shelter Management
> **Build:** `shelters(geo, capacity, flags…)`, `shelter_status` snapshots, `checkins(person split-name, flags, visibility)`. Live occupancy = per-shelter counter in DO (or IncidentRoom map) = checkins − checkouts. Finder = haversine top-N → route-time re-rank. Load balancing = capacity-weighted assignment. QR = `qrcode` npm signed links. Public page = PFIF-safe redacted subset. Daily report = scheduled report template.
> **Deps:** Map System; reunification ties to Missing Persons.

- [x] Shelter registry
- [x] Shelter map
- [x] Shelter capacity tracking
- [x] Shelter occupancy tracking — `DO live counter`
- [x] Shelter availability status
- [x] Shelter accessibility status
- [x] Shelter pet support status
- [x] Shelter medical support status
- [x] Shelter generator status
- [x] Generator fuel-hours remaining
- [x] Shelter water status
- [x] Shelter food status
- [x] Kitchen meal capacity per day
- [x] Shelter sanitation status — `Sphere ratios keyword`
- [x] Shelter staff status
- [x] Shelter staffing roster
- [x] Shelter security status
- [x] Shelter check-in — `QR or manual`
- [x] Shelter check-out
- [x] Bed-level inventory
- [x] Gender-segregated capacity tracking
- [x] Child-friendly space flag
- [x] Family grouping
- [x] Reunification support — `match against Missing Persons`
- [x] Vulnerable person flagging
- [x] Medical needs flagging
- [x] Dietary needs flagging
- [x] Privacy-safe shelter records — `visibility serializer`
- [x] Shelter supply requests — `ICS-213RR keyword → Logistics`
- [x] Shelter incident reports
- [x] Shelter overcrowding alerts — `threshold → notification`
- [x] Shelter transfer workflow
- [x] NGO operator assignment
- [x] Shelter recommendation engine
- [x] Nearest shelter finder
- [x] Best-fit shelter finder — `needs flags match`
- [x] Shelter load balancing
- [x] Shelter route directions
- [x] Shelter public page
- [x] Shelter QR code
- [x] Shelter intake form — `Form Builder schema`
- [x] Shelter daily report
- [x] Shelter closure workflow
- [x] Donation drop-point flag
- [x] Temporary shelter planning
- [x] Mega shelter planning
- [x] Micro shelter planning
- [x] Special needs shelter planning
- [x] Hospital overflow shelter planning

## Field Responder Management
> **Build:** Field app = PWA (Workbox). Location: `watchPosition` → buffered POST (or WS) → `IncidentRoom` DO holds live positions + broadcasts; snapshot to D1 every N sec for history. Offline = IndexedDB (Dexie) outbox + Background Sync API. Geofence/hazard alerts = DO runs `turf.booleanPointInPolygon` against hot zones on each update. Mayday = priority WS broadcast + SMS fallback via Queue. Forms = Form Builder schemas. Fatigue = hours since check-in.
> **Deps:** Map System, Tasks, Offline section.

- [x] Responder registry
- [x] Team registry
- [x] Unit registry
- [x] Vehicle registry
- [x] Equipment registry
- [x] Responder role assignment
- [x] Responder skill tracking — `skill taxonomy table`
- [x] Responder certification tracking — `expiry dates, doc upload`
- [x] Responder availability tracking
- [x] Responder location tracking — `watchPosition → DO`
- [x] Responder status tracking
- [x] Team location tracking
- [x] Vehicle location tracking
- [x] Breadcrumb trail history — `D1 snapshots, time slider`
- [x] Check-in workflow — `ICS-211`
- [x] Check-out workflow
- [x] Shift assignment
- [x] Shift handoff
- [x] Fatigue risk tracking
- [x] Dead-man timer check-ins — `DO alarm; missed = alert chain`
- [x] Buddy/pair accountability tracking
- [x] Safety check reminders
- [x] Mayday alert button — `priority broadcast + SMS fallback`
- [x] Panic alert button
- [x] Field task assignment
- [x] Field task acceptance
- [x] Field task completion
- [x] Field evidence upload — `R2 presigned, EXIF kept`
- [x] Field notes
- [x] Field voice notes — `MediaRecorder → R2; transcript via AI`
- [x] Field photo upload
- [x] Field video upload
- [x] Field offline cache
- [x] Field sync queue — `Dexie outbox`
- [x] Field map download — `PMTiles pack`
- [x] Field route download
- [x] Field checklist
- [x] Field triage form
- [x] Field damage assessment form
- [x] Field trapped-person report
- [x] Field road-blockage report
- [x] Field infrastructure report
- [x] Equipment checkout to responder — `movements ledger reuse`
- [x] Exposure/dosimeter log — `radiological/chemical incidents`
- [x] K9 / specialist team tracking
- [x] Responder heat stress alerts — `heat index threshold`
- [x] Responder air quality alerts — `OpenAQ threshold`
- [x] Responder hazard proximity alerts
- [x] Responder geofence alerts
- [x] Responder accountability report — `PAR keyword`

## Emergency Task Management
> **Build:** `tasks(incident_id, kind, priority, status, geo, assignee(team|user), sla_at, parent_id, deps[])`. SLA/escalation = DO alarm (or Workflow timer) per task firing escalation chain. Auto-priority = deterministic score (severity × vulnerability × age decay × proximity). Auto-assign = nearest available responder with matching skill (H3 distance + status). Conflict/duplicate = same H3 cell + kind + time window. Proof = attachment + verifier approval. Board UI = dnd-kit kanban.
> **Deps:** Core Platform, Field Responder.

- [x] Create emergency tasks
- [x] Assign emergency tasks
- [x] Reassign emergency tasks
- [x] Prioritize emergency tasks
- [x] Escalate emergency tasks — `DO alarm chain`
- [x] Link tasks to map locations
- [x] Link tasks to people
- [x] Link tasks to teams
- [x] Link tasks to shelters
- [x] Link tasks to resources
- [x] Task comments
- [x] Task attachments
- [x] Task status
- [x] Task SLA
- [x] Task due time
- [x] Task dependency
- [x] Task checklist
- [x] Task templates
- [x] Recurring tasks — `cron-spawned from template`
- [x] Task batch creation — `e.g. one per street segment`
- [x] Task import
- [x] Task export
- [x] Task timeline
- [x] Task audit log
- [x] Task conflict detection
- [x] Task duplicate detection
- [x] Task auto-prioritization — `score fn`
- [x] Task auto-routing
- [x] Task auto-assignment — `skill + proximity`
- [x] Task load balancing
- [x] Task swimlanes per team
- [x] WIP limits per team
- [x] Task risk score
- [x] Task impact score
- [x] Task urgency score
- [x] Task command approval
- [x] Task completion proof
- [x] Task verification workflow
- [x] Geofence auto-completion — `arrival closes "reach X" tasks`
- [x] Voice-to-task from field — `voice note → AI extract`
- [x] Task public visibility control

## Requests For Help
> **Build:** All channels → `raw_reports` staging → `help_requests(category, geo, contact, score, status, visibility)`. Public form = Turnstile-protected. Inbound: Twilio/MSG91 SMS webhook, WhatsApp Cloud API, Telegram bot, CF Email Workers, IVR (Exotel/Twilio keypad). Dedupe = phone+geo+time window + embedding similarity. Priority = severity × vulnerability flags × age decay. Fraud = velocity rules + blocklist. Redaction = visibility serializer.
> **Deps:** Data Ingestion, Tasks (assignment), Map System.

- [x] Public request-for-help form — `Turnstile`
- [x] Anonymous help request
- [x] SMS help request
- [x] Email help request
- [x] WhatsApp help request
- [x] Telegram help request
- [x] IVR keypad help request — `press 1 = rescue…`
- [x] Hotline operator entry
- [x] Field responder entry
- [x] Multi-language request form
- [x] Help request map
- [x] Help request deduplication
- [x] Repeat-caller linking — `same phone → same case`
- [x] Help request merge
- [x] Help request priority scoring
- [x] Help request triage
- [x] Help request category
- [x] Rescue request
- [x] Medical request
- [x] Food request
- [x] Water request
- [x] Shelter request
- [x] Transport request
- [x] Missing person request — `routes to Missing Persons`
- [x] Trapped person request
- [x] Animal rescue request
- [x] Accessibility support request
- [x] Help request status tracking
- [x] Help request assignment — `creates linked task`
- [x] Help request verification
- [x] Help request follow-up
- [x] Help request closure
- [x] Help request callback scheduling — `Queue with retry`
- [x] Help request geolocation
- [x] Help request reverse geocoding
- [x] Help request confidence score
- [x] Help request fraud detection
- [x] Help request abuse protection — `rate limit + blocklist`
- [x] Help request public-safe redaction
- [x] Help request heatmap
- [x] Help request surge detection — `rate spike per H3 area`

## Missing Persons And Reunification
> **Build:** Schema PFIF-compatible (Google Person Finder format keyword). Match candidates = fuzzy name (jaro-winkler + double-metaphone, `talisman` npm) + age/sex/geo filters + photo perceptual hash (`blockhash`). All matches require human approval. Sensitive fields encrypted at rest (WebCrypto AES-GCM, keys in Secrets Store). Public listing = redacted consented subset. Keywords: Restoring Family Links (RFL), Safe and Well.
> **Deps:** Shelters (check-in matching), Requests.

- [x] Missing person report
- [x] Found person report
- [x] Family reunification case
- [x] Person photo upload
- [x] Last known location
- [x] Last known time
- [x] Medical condition flag
- [x] Age group flag
- [x] Vulnerability flag
- [x] Privacy-protected public listing
- [x] Internal-only sensitive data — `encrypted columns`
- [x] Case status tracking
- [x] Case notes
- [x] Case assignment
- [x] Duplicate case detection
- [x] Possible match suggestions — `fuzzy name + pHash`
- [x] Shelter check-in matching
- [x] Hospital intake matching
- [x] Unidentified-person (Doe) matching workflow
- [x] Field report matching
- [x] Hotline report matching
- [x] Manual match approval
- [x] Family notification workflow
- [x] Reunification center management
- [x] QR-based reunification card
- [x] Safe-and-well registry
- [x] Foreign national / embassy flag
- [x] Deceased-person handling workflow — `sensitive, restricted role`
- [x] PFIF import/export
- [x] Export reunification report

## Medical And Triage
> **Build:** `facilities` + capacity snapshots (manual entry + API import; FHIR keyword for hospital systems). Triage = START / SALT / JumpSTART enums on Form Builder forms; patient ID = QR wristband. Dispatch = priority queue in DO. MCI mode = stripped bulk-entry UI. Surge forecast = casualty estimate × transport-time model. Privacy = encrypted columns like Missing Persons.
> **Deps:** Map System, Tasks, Population Impact.

- [x] Medical facility registry
- [x] Hospital capacity tracking
- [x] ICU capacity tracking
- [x] Emergency bed tracking
- [x] Ambulance availability tracking
- [x] Medical supply inventory — `Logistics tables reuse`
- [x] Stockpile expiry tracking
- [x] Triage zone map
- [x] Triage patient form — `START/SALT/JumpSTART`
- [x] Patient wristband QR IDs
- [x] Mass casualty incident mode — `bulk entry UI`
- [x] Patient severity classification
- [x] Patient transport request
- [x] Ambulance dispatch queue — `DO priority queue`
- [x] Medical evacuation planning
- [x] Field clinic planning
- [x] Mobile medical unit tracking
- [x] Pharmacy availability tracking
- [x] Oxygen availability tracking
- [x] Blood availability tracking — `e-RaktKosh keyword (India)`
- [x] Medical staff availability tracking
- [x] Disease outbreak monitoring — `case counts, SEIR in Prediction`
- [x] Heat illness monitoring
- [x] Smoke inhalation monitoring
- [x] Waterborne disease risk monitoring
- [x] Mental health / psychosocial support tracking — `MHPSS keyword`
- [x] Medical surge forecast
- [x] Hospital diversion alerts
- [x] Hospital diversion status board
- [x] FHIR import adapter — `HL7 FHIR keyword`
- [x] Public health advisory drafting
- [x] Privacy-safe medical reporting
- [x] Medical incident summary

## Logistics And Resources
> **Build:** `items(sku, name, category, unit)`, `stock(location_id, item_id, qty, lot, expiry)`, append-only `movements` ledger (idempotent; every qty change is a movement). Request → approve → allocate → dispatch → deliver = state machine, long flows via Workflows. Burn rate = rolling avg of movements; forecast = burn × population served. Scanning = `html5-qrcode`. Route planning reuses Evacuation routing engine. Interop keyword: EDXL-RM resource messaging.
> **Deps:** Core Platform; routing from Evacuation.

- [x] Resource inventory
- [x] Supply inventory
- [x] Vehicle inventory
- [x] Equipment inventory
- [x] Generator inventory
- [x] Fuel inventory
- [x] Food inventory
- [x] Water inventory
- [x] Medicine inventory
- [x] PPE inventory
- [x] Tents inventory
- [x] Blankets inventory
- [x] Rescue equipment inventory
- [x] Communication equipment inventory
- [x] Drone inventory
- [x] Boat inventory
- [x] Heavy machinery inventory
- [x] Barcode/QR item scanning — `html5-qrcode`
- [x] Lot/batch tracking
- [x] Expiry tracking and alerts
- [x] Kit/bundle templates — `family kit = item BOM`
- [x] Resource request workflow — `ICS-213RR keyword`
- [x] Resource approval workflow
- [x] Resource allocation workflow
- [x] Resource dispatch workflow
- [x] Resource delivery tracking
- [x] Resource return tracking
- [x] Resource shortage alerts
- [x] Resource surplus alerts
- [x] Resource burn-rate calculation
- [x] Resource demand forecast
- [x] Resource staging area management
- [x] Warehouse management
- [x] Donation intake
- [x] Donation sorting
- [x] Donation matching
- [x] Donation distribution
- [x] Supplier registry
- [x] Procurement request workflow
- [x] Purchase order tracking
- [x] Fleet dispatch
- [x] Vehicle maintenance status
- [x] Driver duty-hours tracking
- [x] Fuel planning
- [x] Cold chain tracking — `temp log fields per movement`
- [x] Customs/clearance tracking — `international aid`
- [x] Supply route optimization
- [x] Last-mile delivery planning
- [x] Air-drop planning
- [x] Boat delivery planning
- [x] Drone delivery planning
- [x] Autonomous delivery planning
- [x] EDXL-RM export

## Infrastructure Impact
> **Build:** `assets(type, geo, status, restore_eta)` + `asset_dependencies(parent, child)` edge table → cascade = BFS over the DAG. Status updates from feeds (Ingestion) + field reports. Seeds from Overture/OSM (substations, towers, hospitals). Maps = layers generated from assets.
> **Deps:** Map System, Data Ingestion.

- [x] Power outage tracking
- [x] Cell service outage tracking
- [x] Internet outage tracking
- [x] Radio outage tracking
- [x] TV broadcast outage tracking
- [x] Road access tracking
- [x] Bridge status tracking
- [x] Railway status tracking
- [x] Airport status tracking
- [x] Port status tracking
- [x] Water supply status tracking
- [x] Sewage system status tracking
- [x] Gas pipeline status tracking
- [x] Fuel station status tracking
- [x] ATM / bank availability tracking
- [x] Hospital infrastructure status
- [x] School infrastructure status
- [x] Shelter infrastructure status
- [x] Critical facility status
- [x] Dam status tracking
- [x] Levee status tracking
- [x] Embankment status tracking
- [x] Debris blockage layer
- [x] Cell tower map — `OpenCelliD keyword`
- [x] Power grid map
- [x] Road closure map
- [x] Utility restoration ETA
- [x] Cell-on-wheels (COW) deployment tracking
- [x] Infrastructure damage reports
- [x] Infrastructure repair tasks
- [x] Infrastructure priority scoring
- [x] Infrastructure dependency graph — `DAG edge table`
- [x] Cascading failure detection — `BFS`
- [x] Critical infrastructure risk forecast
- [x] Public infrastructure advisory

## Weather And Environmental Intelligence
> **Build:** Open-Meteo (free, no key) cron per incident bbox → `weather_obs` / `weather_forecast`. River = USGS NWIS / CWC India-WRIS; air = OpenAQ; lightning = Blitzortung keyword; cyclone tracks = IMD/JTWC bulletins. Indices computed from obs: FWI (fire weather), heat index, flood threshold rules. Impact explanation = AI template citing rows.
> **Deps:** Data Ingestion, Map System.

- [x] Current weather panel — `Open-Meteo`
- [x] Forecast weather panel
- [x] Rainfall tracking
- [x] Wind tracking
- [x] Humidity tracking
- [x] Temperature tracking
- [x] Heat index tracking
- [x] UV index tracking
- [x] Air quality tracking — `OpenAQ`
- [x] River level tracking — `NWIS / CWC`
- [x] Reservoir level tracking
- [x] Tide level tracking
- [x] Storm surge tracking
- [x] Lightning tracking — `Blitzortung`
- [x] Cyclone track import — `IMD / JTWC`
- [x] Fire weather index — `FWI calc`
- [x] Flood risk index
- [x] Landslide risk index — `slope + rainfall threshold`
- [x] Heatwave risk index
- [x] Smoke spread estimate
- [x] Chemical plume estimate — `Gaussian plume, see Prediction`
- [x] Weather impact explanation
- [x] Weather operation risk score
- [x] Weather-based evacuation timing
- [x] Weather-based responder safety alert
- [x] Weather-based shelter recommendation
- [x] Weather-based route recommendation
- [x] Forecast comparison
- [x] Weather confidence scoring
- [x] Manual weather data input
- [x] Weather source comparison

## Prediction And Simulation
> **Build:** Workers CPU-limited → heavy sims run in Cloudflare Containers (or external runner) fed by a Queue; outputs = raster COG / GeoJSON to R2, rendered via geotiff.js or converted to PMTiles. Models (simple first): fire = cellular automata over fuel/slope/wind grid (slope from Copernicus GLO-30 DEM via OpenTopography; serious keyword: Rothermel); flood = bathtub fill of DEM vs water level (HAND keyword); plume = Gaussian plume w/ Open-Meteo wind (ALOHA reference); evac = time-stepped demand assignment on road graph; outbreak = SEIR. `scenarios(params json)` + `scenario_results(snapshot)` for compare/replay.
> **Deps:** Map System, Weather, Evacuation, Population Impact.

- [x] Disaster spread simulation
- [x] Fire spread simulation — `cellular automata; Rothermel keyword`
- [x] Flood spread simulation — `DEM bathtub / HAND`
- [x] Smoke spread simulation
- [x] Chemical plume simulation — `Gaussian plume`
- [x] Dam-break scenario simulation
- [x] Evacuation simulation — `time-stepped graph assignment`
- [x] Shelter demand simulation
- [x] Resource demand simulation
- [x] Hospital surge simulation
- [x] Disease outbreak simulation — `SEIR`
- [x] Road congestion simulation — `BPR`
- [x] Power outage cascade simulation — `dependency DAG BFS`
- [x] Communications outage simulation
- [x] Multi-scenario planning
- [x] Best-case scenario
- [x] Expected-case scenario
- [x] Worst-case scenario
- [x] Confidence bands on forecasts
- [x] Timeline forecast
- [x] Escalation forecast
- [x] De-escalation forecast
- [x] Future evacuation recommendation
- [x] Future responder activity recommendation
- [x] Future shelter opening recommendation
- [x] Future resource staging recommendation
- [x] Simulation replay
- [x] Simulation comparison
- [x] Shareable scenario snapshots
- [x] Simulation confidence score
- [x] Manual simulation parameters
- [x] AI-generated scenario explanation
- [x] What-if planning board
- [x] Red-team scenario mode
- [x] Black-swan scenario mode
- [x] Sci-fi style city-scale digital twin mode — `deck.gl/CesiumJS + live layers`
- [x] Sci-fi style disaster future timeline explorer
- [x] Sci-fi style real-time evacuation outcome predictor
- [x] Sci-fi style command decision consequence simulator

## Communications
> **Build:** `alerts(audience query, channels[], content per-lang, status)` → approval → Workflow fanout → per-channel Queues with per-message idempotency + DLQ. Channels: MSG91/Twilio (SMS, voice w/ TTS), WhatsApp Cloud API templates, FCM + Web Push (VAPID), Resend/SES email, Telegram. Interop: CAP v1.2 export/import — SACHET (India NDMA) / IPAWS (US) keywords; cell broadcast (WEA) is government-gated, integration note only. Delivery status = provider webhooks → `alert_deliveries`. Targeting = polygon → subscriber H3 match, role, shelter, zone.
> **Deps:** Core Platform, Map System (targeting); Public Portal consumes.

- [x] Public alert builder
- [x] Internal alert builder
- [x] SMS alerts — `MSG91/Twilio`
- [x] Email alerts — `Resend/SES`
- [x] WhatsApp alerts — `Cloud API templates`
- [x] Push notifications — `FCM + Web Push VAPID`
- [x] Voice call alerts — `Twilio/Exotel + TTS`
- [x] IVR outbound blast
- [x] Telegram channel alerts
- [x] Radio message drafts
- [x] Ham radio frequency plan export — `ICS-205`
- [x] Loudspeaker/PA script export
- [x] Social media post drafts
- [x] Website banner alerts
- [x] Public status page updates
- [x] Alert approval workflow
- [x] Alert template library
- [x] Multilingual alert generation — `AI translate + review queue`
- [x] AI text-to-speech voice alert generation
- [x] Location-targeted alerts — `polygon → H3 subscriber match`
- [x] Role-targeted alerts
- [x] Shelter-targeted alerts
- [x] Evacuation-zone alerts
- [x] Alert resend
- [x] Alert cancellation
- [x] Alert correction
- [x] Alert read receipts — `tracked links / provider callbacks`
- [x] Alert delivery status
- [x] Alert bounce tracking
- [x] Alert public-safe redaction
- [x] CAP v1.2 export — `SACHET/IPAWS interop`
- [x] CAP v1.2 import relay
- [x] Cell broadcast integration note — `WEA; gov-gated`
- [x] Rumor correction message builder
- [x] Misinformation response drafts
- [x] Press release generator
- [x] Media kit export
- [x] Embeddable alert widget for news sites
- [x] Situation update generator
- [x] Public FAQ generator
- [x] Hotline script generator
- [x] Door-to-door script generator
- [x] Field radio brevity formatter
- [x] Communication blackout fallback plan
- [x] Offline bulletin export
- [x] Printable poster export

## Volunteer Management
> **Build:** Extends responder tables with `kind=volunteer`. Verification = doc upload + admin approve. Badge = QR ID (pdf-lib card). Hours = check-in/out diff. Certificates = pdf-lib template. Geofenced check-in = location within site polygon.
> **Deps:** Field Responder, Tasks.

- [x] Volunteer registration
- [x] Volunteer verification
- [x] Volunteer skill profile
- [x] Volunteer availability
- [x] Volunteer location
- [x] Volunteer assignment
- [x] Volunteer shift scheduling
- [x] Volunteer check-in
- [x] Volunteer check-out
- [x] Geofenced volunteer check-in
- [x] Volunteer task board
- [x] Volunteer training status
- [x] Volunteer skills quiz — `Form Builder scored form`
- [x] Volunteer credential upload
- [x] Volunteer background status
- [x] Minor-volunteer guardian consent
- [x] Volunteer insurance status flag
- [x] Volunteer safety briefing
- [x] Volunteer incident reporting
- [x] Volunteer team grouping
- [x] Volunteer supervisor assignment
- [x] Volunteer communication
- [x] Volunteer hours tracking
- [x] Volunteer ID badge generation — `QR`
- [x] Volunteer certificate generation
- [x] Volunteer abuse prevention
- [x] Volunteer duplicate detection
- [x] Spontaneous volunteer intake
- [x] Community organization registry
- [x] NGO coordination
- [x] Mutual aid coordination — `see Multi-Agency section`

## Damage Assessment
> **Build:** Typed Form Builder forms per asset class. Severity = FEMA PDA categories keyword (affected / minor / major / destroyed). Photo verification = EXIF GPS vs tagged location match. Before/after = `react-compare-slider`. Loss estimate = unit-cost library × quantities. AI vision = provider vision model describing damage from images (draft, human-verified).
> **Deps:** Field Responder (forms), Drone (imagery), Map System.

- [x] Building damage assessment
- [x] Road damage assessment
- [x] Bridge damage assessment
- [x] Utility damage assessment
- [x] Crop damage assessment
- [x] Industrial damage assessment
- [x] Shelter damage assessment
- [x] Hospital damage assessment
- [x] School damage assessment
- [x] Damage severity scoring — `FEMA PDA categories`
- [x] Damage photo upload
- [x] Damage video upload
- [x] Damage location tagging
- [x] Geotag verification — `EXIF GPS vs pin distance`
- [x] Damage verification workflow
- [x] Damage assessment map
- [x] Damage assessment checklist
- [x] Damage assessment forms
- [x] Rapid needs assessment
- [x] Detailed needs assessment
- [x] Loss estimate — `unit-cost library`
- [x] Repair cost library — `configurable unit costs`
- [x] Repair priority scoring
- [x] Recovery planning — `see Recovery section`
- [x] Insurance-safe export
- [x] Insurance claim packet export
- [x] Government report export
- [x] Donor report export
- [x] Before-after image comparison — `react-compare-slider`
- [x] Drone damage survey import
- [x] Satellite damage survey import — `Copernicus EMS grading maps`
- [x] AI damage description from images — `vision model`
- [x] AI damage report summary

## Drone And Remote Sensing
> **Build:** `missions`, `flights`, media → R2. Orthomosaic = WebODM (external/container) → COG → R2 → map overlay (geotiff.js or tile to PMTiles). Detections = vision-model Queue → flagged-points layer (draft, human-confirm). Search patterns = generated waypoint grids — expanding square, parallel track keywords — export KML/GeoJSON. Live drone position = same DO pipeline as responders.
> **Deps:** Map System, AI Configuration, Damage Assessment.

- [x] Drone mission planner
- [x] Drone survey zones
- [x] Drone flight logs
- [x] Drone image upload
- [x] Drone video upload
- [x] Drone thermal image upload
- [x] Drone map overlay — `COG on R2`
- [x] Orthomosaic processing pipeline — `WebODM`
- [x] Drone live location
- [x] Drone battery tracking
- [x] Drone operator assignment
- [x] Drone no-fly zone warnings
- [x] Drone evidence tagging
- [x] Drone search pattern planning — `expanding square / parallel track`
- [x] Search pattern waypoint export — `KML/GeoJSON`
- [x] Drone damage detection workflow — `vision model queue`
- [x] Drone trapped-person flagging
- [x] Drone flood extent mapping
- [x] Drone fire edge mapping
- [x] Drone landslide mapping
- [x] Satellite imagery import — `Sentinel Hub / Copernicus`
- [x] Satellite change detection
- [x] Remote sensing confidence score
- [x] Sci-fi style autonomous drone swarm task planner
- [x] Sci-fi style thermal survivor hint layer — `vision model on thermal frames`
- [x] Sci-fi style automatic safe landing zone detector
- [x] Sci-fi style live 3D disaster map from drone feeds — `CesiumJS`

## Public Portal
> **Build:** Separate unauthenticated Worker routes; aggressive KV/cache. Renders only `visibility=public` data through the public serializer — enforced in one place. PWA installable; one-file HTML fallback (see Offline). SMS info = inbound keyword autoresponder. Outbound feeds = public CAP/RSS. i18n static strings.
> **Deps:** Communications, Shelters, Map System.

- [x] Public incident page
- [x] Public map
- [x] Public alerts
- [x] Public CAP/RSS feed
- [x] Public shelter finder
- [x] Public evacuation route finder
- [x] Public safety instructions
- [x] Public report submission — `Turnstile`
- [x] Public missing person submission
- [x] Public donation page
- [x] Public volunteer signup
- [x] Public FAQ
- [x] Public multilingual content
- [x] Public low-bandwidth page — `no JS fallback`
- [x] Public printable instructions
- [x] Public SMS instructions — `keyword autoresponder`
- [x] Public IVR info line
- [x] Public rumor reporting
- [x] Public status update subscription — `location polygon subscribe`
- [x] Public privacy notice
- [x] Public accessibility mode
- [x] Public screen-reader optimized pages
- [x] Public offline downloadable packet
- [x] Public PWA install
- [x] Kiosk display mode
- [x] Embeddable public widgets
- [x] Public safe-route guidance
- [x] Public family check-in
- [x] Public safe-and-well registry
- [x] Public donation needs list
- [x] Public trusted source links

## Reports And Documents
> **Build:** Report = template (Markdown + `{{query}}` placeholders) + frozen data snapshot → render md → HTML → PDF via Cloudflare Browser Rendering (print CSS); form-style PDFs via pdf-lib; DOCX via `docx` npm. ICS form pack mapping: 201, 202, 203, 204, 205, 206, 209, 211, 214. Versions table; share = signed-token links; schedule = Cron Triggers.
> **Deps:** everything it reports on; AI Configuration for drafts.

- [x] Situation report
- [x] Incident action plan — `ICS-202+204 pack`
- [x] Operational period report
- [x] Evacuation report
- [x] Shelter report
- [x] Resource report
- [x] Medical report
- [x] Infrastructure report
- [x] Weather impact report
- [x] Damage assessment report
- [x] Volunteer report
- [x] Missing persons report
- [x] Public communication report
- [x] After-action report
- [x] ICS form pack export — `201/202/204/205/209/214`
- [x] 3W report — `who-what-where, humanitarian keyword`
- [x] HXL-tagged CSV export — `Humanitarian Exchange Language`
- [x] OCHA-style donor sitrep format
- [x] Executive summary
- [x] Technical appendix
- [x] Map appendix
- [x] Timeline appendix
- [x] Source appendix
- [x] Data quality appendix
- [x] Decision log appendix
- [x] AI-generated report drafts
- [x] Human approval workflow
- [x] Report version history
- [x] Report comments
- [x] Report export to PDF — `Browser Rendering`
- [x] Report export to DOCX — `docx npm`
- [x] Report export to Markdown
- [x] Report export to JSON
- [x] Report export to CSV
- [x] Report sharing link — `signed token`
- [x] Public-safe report export
- [x] Confidential report export
- [x] Auto-scheduled reports — `Cron`
- [x] Report template library
- [x] Custom report builder

## Analytics
> **Build:** Hot path: write events to Workers Analytics Engine (blobs + doubles). Dashboards: nightly Cron aggregates into D1 rollup tables; charts = ECharts. Custom dashboards = saved JSON layouts of widget queries. Exports = CSV from rollups.
> **Deps:** Core Platform; data from all sections.

- [x] Incident analytics
- [x] Response analytics
- [x] Population analytics
- [x] Evacuation analytics
- [x] Shelter analytics
- [x] Resource analytics
- [x] Medical analytics
- [x] Volunteer analytics
- [x] Communications analytics — `alert reach vs population`
- [x] Infrastructure analytics
- [x] Weather analytics
- [x] Damage analytics
- [x] Task analytics
- [x] SLA analytics
- [x] Team performance analytics
- [x] Responder utilization analytics
- [x] Help-request lifecycle funnel
- [x] Bottleneck analytics
- [x] Trend analytics
- [x] Geographic analytics — `H3 rollups`
- [x] Time-series analytics
- [x] Heatmap analytics
- [x] Comparison analytics
- [x] Cross-incident cohort comparison
- [x] Scenario analytics
- [x] Data quality analytics
- [x] Source reliability analytics
- [x] AI usage analytics
- [x] API usage analytics
- [x] Cost analytics
- [x] Custom dashboards
- [x] Custom metrics
- [x] Saved views
- [x] Scheduled analytics emails
- [x] Export analytics data

## Decision Support
> **Build:** Recommendation engines = deterministic scoring functions over real data + AI memo on top (memo must cite row IDs; citations validated to exist). `decisions` = append-only, hash-chained (Conventions). Sign-off = role-gated approval. Alternatives/consequences = linked scenario snapshots from Prediction.
> **Deps:** Prediction, Analytics, AI Configuration.

- [x] Priority recommendation engine — `score fn + AI memo`
- [x] Evacuation recommendation engine
- [x] Shelter recommendation engine
- [x] Resource recommendation engine
- [x] Responder recommendation engine
- [x] Route recommendation engine
- [x] Medical priority recommendation engine
- [x] Infrastructure priority recommendation engine
- [x] Public alert recommendation engine
- [x] Missing data recommendation engine
- [x] Decision memo generator
- [x] Decision approval workflow
- [x] Decision log — `append-only, hash chain`
- [x] Decision rationale
- [x] Decision source links
- [x] Decision confidence score
- [x] Decision risk score
- [x] Decision impact estimate
- [x] Decision alternatives
- [x] Decision consequence preview — `scenario snapshot link`
- [x] Decision tradeoff matrix builder
- [x] Decision premortem prompt
- [x] Dissent / objection log
- [x] Decision rollback notes
- [x] Commander sign-off
- [x] Legal review flag
- [x] Public communication flag
- [x] Ethics review flag
- [x] AI-assisted decision draft
- [x] Human-only final approval
- [x] Sci-fi style command center advisor
- [x] Sci-fi style disaster chess engine
- [x] Sci-fi style millions-of-possible-response-plans comparison
- [x] Sci-fi style one-click optimal response plan draft

## Search And Knowledge Base
> **Build:** D1 FTS5 virtual tables per entity + one unified `/search` endpoint with permission filters. Semantic = Vectorize w/ configured embeddings; AI answers = RAG (top-k chunks, mandatory citations). KB = versioned Markdown docs. OCR'd attachment text indexed too.
> **Deps:** AI Configuration, Data Ingestion (OCR).

- [x] Global search — `FTS5 union endpoint`
- [x] Incident search
- [x] Map object search
- [x] Person search
- [x] Shelter search
- [x] Resource search
- [x] Task search
- [x] Report search
- [x] Document search
- [x] Attachment search — `OCR text indexed`
- [x] Semantic search — `Vectorize`
- [x] Saved searches
- [x] Search filters
- [x] Search permissions
- [x] Incident knowledge base
- [x] SOP knowledge base
- [x] KB document versioning
- [x] SOP review-expiry reminders — `cron`
- [x] Disaster playbook library
- [x] Local laws library
- [x] Agency contacts library
- [x] Shelter operations guide
- [x] Evacuation guide
- [x] Medical triage guide
- [x] Logistics guide
- [x] Communications guide
- [x] AI knowledge base assistant — `RAG, citations required`
- [x] AI source-grounded answers
- [x] AI document summarization
- [x] AI checklist extraction
- [x] AI glossary generation

## Integrations
> **Build:** Every integration = thin adapter module behind an interface + `integrations(kind, config json, enabled, secrets-ref)` registry row. Inbound webhooks HMAC-verified; outbound retried via Queues. Free-first defaults flagged below.
> **Deps:** Core Platform.

- [x] OpenAI-compatible AI provider integration
- [x] Custom AI base URL integration
- [x] Custom AI API key integration
- [x] Workers AI integration — `zero-key fallback`
- [x] Weather API integration — `Open-Meteo (free, no key)`
- [x] NASA FIRMS fire detection integration
- [x] USGS earthquake feed integration
- [x] GDACS global alert integration
- [x] OpenAQ air quality integration
- [x] Copernicus EMS / Sentinel Hub integration
- [x] IMD / CWC India feed integration
- [x] SACHET (NDMA India) CAP integration
- [x] Bhuvan (ISRO) layer integration
- [x] Map tile provider integration — `PMTiles default`
- [x] Geocoding provider integration — `Nominatim/Photon/Pelias`
- [x] what3words integration
- [x] SMS provider integration — `MSG91/Twilio adapter`
- [x] Voice/IVR provider integration — `Exotel/Twilio`
- [x] Email SMTP integration — `Resend/SES`
- [x] WhatsApp provider integration — `Cloud API / Gupshup BSP`
- [x] Telegram bot integration
- [x] Push notification integration — `FCM + VAPID`
- [x] Webhook integration
- [x] Slack integration
- [x] Discord integration
- [x] Microsoft Teams integration
- [x] Google Sheets import
- [x] Airtable import
- [x] ArcGIS import — `ArcGIS REST / FeatureServer`
- [x] WMS/WFS layer integration — `OGC keywords`
- [x] QGIS export
- [x] GeoServer export
- [x] OpenStreetMap integration — `Overpass API`
- [x] Overture Maps data integration
- [x] FEMA-style data import
- [x] Government API import
- [x] NGO database import
- [x] Hospital system import — `FHIR`
- [x] Shelter system import
- [x] Volunteer platform import
- [x] Drone platform import
- [x] IoT sensor import — `MQTT bridge keyword`
- [x] Radio dispatch system export
- [x] Emergency call center export
- [x] Public alerting system export — `CAP`
- [x] Sahana Eden / Ushahidi import — `prior-art interop`
- [x] Single sign-on integration
- [x] SAML integration — `WorkOS keyword`
- [x] OIDC integration
- [x] Clerk authentication integration
- [x] Custom auth integration

## Security
> **Build:** Turnstile on public forms; sessions httpOnly + `devices` table; MFA/passkeys via auth provider (WebAuthn). Permissions = policy middleware + field-level serializers. PII = detect (regex + NER prompt) → mask map. Sensitive columns encrypted (WebCrypto AES-GCM, keys in Secrets Store, rotation job). Audit = hash chain (Conventions). Rate limit = token-bucket DO. Break-glass = time-boxed elevated role grant + loud alert + immutable log entry.
> **Deps:** Core Platform; continuous hardening.

- [x] Secure authentication
- [x] Multi-factor authentication
- [x] Passkey support — `WebAuthn`
- [x] Single sign-on
- [x] Session management
- [x] Device management
- [x] Anomalous login detection — `new device/geo alert`
- [x] Role-based permissions
- [x] Attribute-based permissions
- [x] Field-level permissions — `serializer whitelists`
- [x] Incident-level permissions
- [x] Map-layer permissions
- [x] Report permissions
- [x] Public-private data separation
- [x] Sensitive data labels
- [x] PII masking
- [x] PII detection
- [x] PII redaction
- [x] Location privacy protection — `coordinate fuzzing on public`
- [x] Medical privacy protection
- [x] Missing person privacy protection
- [x] Audit logs
- [x] Immutable decision log — `hash chain`
- [x] Admin action log
- [x] API access log
- [x] AI request audit log
- [x] Data export audit log
- [x] Export watermarking — `user+ts stamp on PDFs`
- [x] Encryption in transit
- [x] Encryption at rest — `AES-GCM sensitive columns`
- [x] Secret storage — `wrangler secrets / Secrets Store`
- [x] API key vault
- [x] AI key vault
- [x] Key rotation schedule
- [x] Webhook signing — `HMAC header`
- [x] Rate limiting — `token-bucket DO`
- [x] Abuse prevention
- [x] Bot protection — `Turnstile`
- [x] Public form spam protection
- [x] IP allowlist
- [x] Security headers / CSP
- [x] Signed URL expiry policy
- [x] Emergency access mode
- [x] Break-glass admin access — `time-boxed + alert + log`
- [x] Security incident mode
- [x] Data retention policy
- [x] Data deletion workflow
- [x] Legal hold — `blocks retention purge`
- [x] Backup restore
- [x] Disaster recovery plan

## Compliance And Governance
> **Build:** `retention_policies` table (data_class, ttl_days) + nightly cron purge; `legal_holds` table blocks purge by entity ref. Consent = `consents` table (subject, purpose, granted_at, revoked_at). DSR (data subject request) export/delete = Workflow: gather rows across tables by person ref → JSON/PDF export or anonymize-in-place. Approvals reuse the generic approval workflow (Conventions). Transparency page = public route rendering AI policy, providers, retention from config. Chain-of-custody = hash-chained `evidence_events` per attachment.
> **Deps:** Security; Reports.

- [x] Organization policy settings
- [x] Data retention rules — `per data_class TTL + cron purge`
- [x] Data classification — `public/internal/sensitive enum`
- [x] Sensitive data handling
- [x] Consent tracking — `consents table, purpose-scoped`
- [x] Data subject access request export — `DSR Workflow, cross-table gather`
- [x] Data subject deletion request — `anonymize-in-place, keep aggregates`
- [x] Data processing register — `purposes × data classes table`
- [x] Subprocessor list page — `CF, AI provider, SMS provider`
- [x] DPDP Act readiness notes — `India keyword; GDPR analog`
- [x] Inter-org data sharing agreement tracker — `MOU records w/ scope+expiry`
- [x] Public data approval
- [x] Report approval
- [x] Alert approval
- [x] Decision approval
- [x] Audit export
- [x] Incident closure review
- [x] After-action review
- [x] SOP compliance checklist
- [x] Accessibility compliance — `see Accessibility section`
- [x] Localization compliance
- [x] Government report format support
- [x] NGO report format support
- [x] Donor report format support
- [x] Privacy impact report
- [x] AI usage policy
- [x] AI risk disclosure
- [x] Human-in-the-loop enforcement — `review_status gate, no auto-publish`
- [x] Model provider disclosure
- [x] Public transparency page
- [x] Evidence chain-of-custody — `hash-chained evidence_events`
- [x] Tamper-evident logs — `hash chain + periodic anchor export`

## Billing-Free SaaS Admin Features
> **Build:** Limits = counters in KV/DO checked in middleware (per-org: API calls, AI tokens, storage bytes, incidents); over-limit → 429 + admin banner, never hard-block active incident ops (grace mode). Feature flags = `flags` table (global/org/incident scope) cached in KV 60s; gate routes + UI. Templates = JSON blobs in D1 with `kind` enum, instantiate = deep-copy. Form builder per Conventions (JSON-Schema). Monitors read CF GraphQL Analytics API + own `job_runs`/`webhook_deliveries` tables. Impersonation = admin assumes org-scoped session, consent + audit row, banner shown.
> **Deps:** Core Platform.

- [x] Organization creation
- [x] Organization invitation
- [x] Member management
- [x] Workspace management
- [x] Usage limits — `KV/DO counters in middleware`
- [x] Storage limits — `sum R2 object sizes per org`
- [x] API limits
- [x] AI request limits — `token counter per org`
- [x] Incident limits
- [x] Export limits
- [x] Grace mode during active incidents — `soft-limit, never block ops`
- [x] Feature flags — `D1 + KV cache, scope global/org/incident`
- [x] Maintenance mode
- [x] System announcements — `banner table + dismiss state`
- [x] Admin notifications
- [x] Global configuration
- [x] Tenant configuration
- [x] Tenant impersonation with consent log — `audit + visible banner`
- [x] Exercise tenant toggle — `marks org as drill/sandbox`
- [x] Incident templates
- [x] Disaster type templates
- [x] Report templates
- [x] Alert templates
- [x] Task templates
- [x] Map layer templates
- [x] Form builder — `JSON-Schema + react-jsonschema-form`
- [x] Custom fields
- [x] Custom statuses
- [x] Custom tags
- [x] Custom workflows — `state machine JSON per entity kind`
- [x] Audit viewer
- [x] Error logs
- [x] Health checks — `/healthz deep-check D1/R2/Queues`
- [x] Background job monitor — `job_runs table UI`
- [x] Queue monitor — `depth + DLQ count via GraphQL API`
- [x] Webhook monitor — `webhook_deliveries status board`
- [x] AI monitor — `latency/error/token charts`
- [x] Data sync monitor — `feed last_success_at staleness`
- [x] Cron job registry UI — `list schedules + last run + force-run`

## Developer Platform
> **Build:** All routes via chanfana → OpenAPI auto-spec at `/openapi.json`; docs UI = Scalar/Swagger embed. API keys = `sk_live_` prefix + sha256 hash stored, scopes array, last_used_at; service accounts = keys not bound to a human user. Webhooks = `webhook_subscriptions` (url, events[], secret) + Queue-driven delivery with HMAC `X-Signature`, exponential retries, `webhook_deliveries` log + replay button. Event stream = SSE endpoint backed by the IncidentRoom DO broadcast. Generators = faker-js seeded scripts writing realistic incidents/shelters/population via the normal API (dogfood). SDK = openapi-typescript from the spec.
> **Deps:** Core Platform; OpenAPI from day 1.

- [x] Public API
- [x] Admin API
- [x] Incident API
- [x] Map API
- [x] Shelter API
- [x] Evacuation API
- [x] Resource API
- [x] Task API
- [x] Report API
- [x] AI API
- [x] Webhook API
- [x] OpenAPI spec — `chanfana auto-generated`
- [x] API docs — `Scalar embed of /openapi.json`
- [x] API playground
- [x] API key creation — `sk_ prefix + sha256 hash`
- [x] API key rotation
- [x] Scoped API keys — `scopes[] checked in middleware`
- [x] Service accounts
- [x] Webhook subscriptions — `events[] filter`
- [x] Webhook retry logs — `webhook_deliveries table`
- [x] Webhook replay UI — `re-enqueue stored payload`
- [x] Webhook signing secret — `HMAC X-Signature`
- [x] Event stream API — `SSE from IncidentRoom DO`
- [x] Import API
- [x] Export API
- [x] Bulk operations API — `NDJSON batch endpoints`
- [x] SDK-ready schema — `openapi-typescript gen`
- [x] CLI-ready API
- [x] Bruno/Postman collection export — `from OpenAPI spec`
- [x] Sandbox environment — `wrangler env w/ synthetic data`
- [x] Local development seed data — `faker-js seed script`
- [x] Test incident generator
- [x] Mock disaster data generator
- [x] Synthetic population generator — `random H3 weights`
- [x] Synthetic shelter generator
- [x] Synthetic resource generator
- [x] Synthetic map layer generator
- [x] Synthetic feed replayer — `replay stored GeoJSON ticks`
- [x] AI prompt test harness
- [x] API rate limit dashboard
- [x] API changelog

## Offline And Resilience
> **Build:** PWA via Workbox: precache shell, runtime cache API GETs (stale-while-revalidate). Writes → Dexie (IndexedDB) outbox → Background Sync flush with idempotency keys; conflicts = LWW + per-field merge UI for flagged entities. Map offline = PMTiles region packs downloaded to OPFS, MapLibre reads via service-worker range handler. "Incident pack" endpoint = one JSON bundle (tasks, shelters, routes, contacts) + one-file HTML packet (inline CSS/JS/data, works from file://). QR packets = chunked JSON (~2KB/code) + index header. Degraded modes = feature flags gating subsystems (AI off, map off, read-only) toggled by admin or health checks. SMS/email fallback reuses Communications providers.
> **Deps:** Core Platform; Field Responder; Map System.

- [x] Offline public pages — `Workbox precache`
- [x] Offline field app mode
- [x] Offline map tiles — `PMTiles packs in OPFS`
- [x] Offline region pack manager — `download/update/delete per area`
- [x] Offline shelter list
- [x] Offline evacuation routes
- [x] Offline task list
- [x] Offline forms — `JSON-Schema renders offline`
- [x] Offline report drafts
- [x] Offline attachment queue — `blobs in IndexedDB, upload on sync`
- [x] Offline sync conflict resolution — `LWW + per-field merge UI`
- [x] Low-bandwidth sync — `delta since cursor, gzip`
- [x] SMS fallback
- [x] Email fallback
- [x] Printable fallback packets
- [x] QR code data packets — `chunked JSON ~2KB/code`
- [x] Incident pack download endpoint — `one JSON bundle for field kit`
- [x] Local cache
- [x] Edge cache — `Cache API on public GETs`
- [x] Static emergency page fallback — `CF custom error page / Worker static`
- [x] Incident snapshot export
- [x] One-file HTML emergency packet — `inline data, opens from file://`
- [x] Peer-to-peer field sync — `WebRTC DataChannel, LAN-first`
- [x] USB/SD sneakernet bundle — `import/export signed zip`
- [x] Backup command dashboard — `read-only mirror page`
- [x] Read-only degraded mode — `flag gates all writes`
- [x] AI-disabled degraded mode
- [x] Map-disabled degraded mode — `table fallbacks everywhere`
- [x] Public portal degraded mode — `static rendered snapshot`
- [x] Database restore workflow — `D1 time-travel / R2 dump restore`
- [x] Emergency data export
- [x] Emergency data import

## Sci-Fi But Possible Features
> **Build:** None of these need new infrastructure — they are compositions of earlier primitives. Digital twin = MapLibre/deck.gl (or CesiumJS 3D) stacking every live layer + time slider. Plan generators = chained AI calls over structured incident JSON (gather context → draft sections → critique pass → assemble), always landing as `draft` for human approval. Debate/red-team = N parallel drafts with different system prompts + judge prompt scoring. Probability maps = scoring formula over H3 cells (reports × population × hazard × time decay) rendered as heat layer. Thermal hints = vision model on uploaded frames → flagged boxes → human review queue. Mesh/phone-to-phone = WebRTC + the offline outbox. Voice = Web Speech API (STT) + TTS provider from AI Config. Predictive positioning = demand forecast per H3 zone → suggest staging moves. Build these LAST (P14).
> **Deps:** everything; pure composition layer.

- [x] City-scale live disaster digital twin — `deck.gl/CesiumJS + all live layers + time slider`
- [x] AI-generated full emergency response plan in seconds — `chained drafts → IAP template`
- [x] Multi-agent command simulation — `N role-prompted agents + shared state JSON`
- [x] Simulated evacuation of every household — `building footprints × routing, Containers job`
- [x] Hyperlocal risk score for every building — `hazard × exposure × vulnerability per footprint`
- [x] Hyperlocal rescue priority score for every street — `requests × population × access`
- [x] Real-time safe corridor generation — `routing graph minus hazard H3 cells`
- [x] Automatic drone swarm route planner — `area decomposition → waypoint sets per drone`
- [x] Automatic trapped-person probability map — `report density × building damage × time`
- [x] Automatic casualty surge prediction — `triage counts trend → hospital load forecast`
- [x] Automatic panic-spread prediction from public reports — `report velocity per zone`
- [x] Automatic misinformation outbreak detector — `embedding clusters of rumor reports`
- [x] Automatic supply chain collapse predictor — `burn rate vs inbound deliveries`
- [x] Automatic infrastructure cascade failure predictor — `dependency graph BFS`
- [x] Automatic shelter overflow prevention engine — `occupancy trend → rebalance suggestions`
- [x] Automatic responder danger prediction — `position vs hazard spread forecast`
- [x] Automatic command decision stress test — `premortem prompt vs decision memo`
- [x] Automatic route reopening prediction — `repair tasks ETA → graph updates`
- [x] Automatic public mood analysis from reports — `sentiment classify, aggregate only`
- [x] AI-generated multilingual voice briefings — `briefing → translate → TTS`
- [x] AI-generated radio-ready command scripts — `brevity formatter prompt`
- [x] AI-generated interactive public evacuation assistant — `chat over public-safe data only`
- [x] AI-generated personalized evacuation instructions — `address → zone → route → steps`
- [x] AI-generated family reunification match hints — `embedding + fuzzy name match, human approve`
- [x] AI-generated live disaster timeline reconstruction — `events → narrative prompt`
- [x] AI-generated recovery cost estimate — `damage records × cost library`
- [x] AI-generated donation demand forecast — `needs registry trend`
- [x] AI-generated future disaster risk memory — `lessons-learned embeddings recalled on new incident`
- [x] Satellite-plus-drone real-time 3D damage map — `orthomosaic + change detection on Cesium`
- [x] Live thermal survivor hinting from drone imagery — `vision model → review queue, never auto-task`
- [x] Predictive ambulance positioning — `medical request forecast per zone`
- [x] Predictive generator positioning
- [x] Predictive food and water staging
- [x] Predictive shelter opening — `evac forecast vs capacity`
- [x] Predictive evacuation reversal detection — `movement reports against flow`
- [x] Automatic "next 6 hours" command briefing — `cron + briefing prompt`
- [x] Automatic "next 24 hours" operational plan
- [x] Automatic "next 7 days" recovery plan
- [x] One-click command center briefing room — `war-room layout + auto-brief`
- [x] One-click public-safe situation portal — `publish snapshot pipeline`
- [x] One-click after-action report from all incident data — `AAR prompt over full timeline`
- [x] One-click disaster replay video from timeline and map data — `frame capture + Containers ffmpeg`
- [x] One-click policy compliance review — `SOP checklist vs incident events prompt`
- [x] One-click impossible-scenario stress test — `black-swan param sets`
- [x] One-click best-response plan comparison — `tradeoff matrix over N drafts`
- [x] One-click full-city evacuation simulation — `Containers batch job`
- [x] Voice-controlled incident command — `Web Speech API → command palette intents`
- [x] Hands-free responder assistant — `voice in/out + tasks readback`
- [x] AR-style field responder map export — `GeoJSON/KML for AR apps`
- [x] Wearable responder status integration — `webhook ingest, heart-rate alerts`
- [x] Smart helmet camera data import — `video upload + frame analysis`
- [x] Sensor-fusion disaster intelligence layer — `all feeds scored into one H3 risk surface`
- [x] Community mesh-network report sync — `WebRTC local-first relay`
- [x] Offline phone-to-phone incident sync — `WebRTC DataChannel outbox swap`
- [x] Disaster memory graph across historical incidents — `cross-incident entity links + embeddings`
- [x] Response strategy recommendation based on past disasters — `similar-incident retrieval`
- [x] AI commander debate mode with multiple response strategies — `N drafts + judge`
- [x] AI red-team vs blue-team disaster planning — `adversary prompt vs plan`
- [x] AI ethical-risk reviewer for evacuation decisions — `checklist prompt, flags only`
- [x] AI public trust score for outgoing alerts — `clarity/actionability rubric prompt`
- [x] AI contradiction detector across all reports — `pairwise NLI prompt on clusters`
- [x] AI unknown-unknowns detector — `coverage gaps vs playbook expectations`
- [x] AI "what are we missing" command advisor — `checklist diff prompt per op period`

## Multi-Agency Coordination And Mutual Aid *(new section)*
> **Build:** `agencies` registry (org-linked or external stub) + `mous` (scope, expiry, signed doc in R2). Cross-org sharing = `incident_shares` (incident_id, target_org, scope: layers[]/panels[]) enforced in policy middleware; shared layers are read-only mirrors. Inter-org resource requests = EDXL-RM-shaped records routed via webhook/email to target org. Liaison = role scoped to one incident in a foreign org. Regional dashboard = aggregator Worker reading multiple orgs the user belongs to. Unified command = one incident, multiple command-owner orgs, dual approval on key actions.
> **Deps:** Core Platform; Logistics; Communications.

- [x] Agency registry — `internal orgs + external stubs`
- [x] Agency capability profile — `resources, skills, coverage area`
- [x] MOU / mutual aid agreement tracker — `scope + expiry + doc`
- [x] Liaison officer role — `single-incident foreign-org access`
- [x] Cross-org incident sharing — `incident_shares scope grants`
- [x] Shared layer publishing — `read-only mirror layers`
- [x] Shared panel publishing — `pick panels visible to partner`
- [x] Inter-org resource request — `EDXL-RM record + webhook`
- [x] Inter-org resource offer
- [x] Mutual aid deployment tracking — `who sent what where`
- [x] Unified command mode — `multi-org command, dual approval`
- [x] Joint information center workspace — `shared PIO drafts`
- [x] Inter-agency contact directory
- [x] Inter-agency chat channel — `DO room scoped to share`
- [x] Regional multi-incident dashboard — `cross-org rollup`
- [x] Agency performance debrief — `post-incident, private`

## Training Drills And Exercises *(new section)*
> **Build:** `exercise_mode` flag on incident → loud persistent banner, all comms watermarked "DRILL", external send disabled or routed to sim inbox. Scenario = `injects` table (t_offset, kind, payload) executed by Workflow timer into the normal ingest path. Sim-cell console = inject editor + manual fire + pause/resume clock. Feed replay = stored feed snapshots re-emitted on schedule. Evaluation = HSEEP-style EEG forms (Form Builder) bound to objectives; AAR auto-drafts from exercise timeline. Teardown = cascade-delete exercise data or archive to exercise org.
> **Deps:** Incident Creation; Data Ingestion; Reports.

- [x] Exercise mode incident flag — `banner + DRILL watermark`
- [x] External comms lockout in exercises — `sim inbox instead of send`
- [x] Scenario builder — `inject list w/ time offsets`
- [x] Inject scheduler — `Workflow fires injects into ingest`
- [x] Sim-cell console — `manual inject, pause/resume clock`
- [x] Feed replay engine — `re-emit stored feed snapshots`
- [x] Tabletop exercise mode — `discussion prompts, no field ops`
- [x] Functional / full-scale exercise mode
- [x] Exercise objectives tracker — `HSEEP keyword`
- [x] Evaluator forms — `EEG-style, Form Builder`
- [x] Evaluator observation log
- [x] Participant roster + sign-in
- [x] Exercise timeline capture — `auto from events`
- [x] Exercise after-action report — `AAR draft from timeline`
- [x] Improvement plan tracker — `findings → tasks w/ owners`
- [x] Exercise data teardown — `cascade delete or archive`
- [x] Drill performance comparison — `across exercises`

## Early Warning And Community Preparedness *(new section)*
> **Build:** `watches` (hazard, polygon GeoJSON+H3, state: monitoring/advisory/watch/warning) promoted manually or by threshold rules (`gauge X > level Y for Z min` evaluated by cron over feed data). Public subscriptions = point/polygon + channel prefs; alert fan-out reuses Communications. Pre-registry = opt-in vulnerable household records (consent-tracked, sensitive class). Checklists/family plan = JSON templates rendered public, saved per household, printable. Preparedness score = ward-level composite (subscriptions, drills done, shelters mapped). SACHET/CAP relay = ingest official CAP, mirror to subscribers.
> **Deps:** Communications; Weather; Map System; Compliance (consent).

- [x] Hazard watch states — `monitoring→advisory→watch→warning`
- [x] Watch polygon definition — `GeoJSON + H3 cover`
- [x] Threshold auto-watch rules — `gauge>level for N min → promote`
- [x] Official CAP feed relay — `SACHET/IPAWS ingest → mirror`
- [x] Public location subscriptions — `point/polygon + channels`
- [x] Subscription alert fan-out — `reuse Communications targeting`
- [x] Vulnerable household pre-registry — `opt-in, consent, sensitive`
- [x] Pre-registry evacuation assist matching — `feeds door-to-door tasking`
- [x] Household preparedness checklist — `go-bag, docs, meds`
- [x] Family emergency plan builder — `contacts, meeting points, printable`
- [x] School drill scheduler — `term calendar + participation log`
- [x] Community siren registry — `location + coverage + test log`
- [x] Seasonal preparedness campaigns — `scheduled content pushes`
- [x] Ward preparedness score — `composite metric + leaderboard`
- [x] Pre-disaster shelter mapping drive — `crowdsource + verify queue`
- [x] Pre-incident risk briefs — `monsoon/cyclone season memos`

## Recovery And Rehabilitation *(new section)*
> **Build:** `needs_registry` (household, needs[], assessed_at) seeded from damage + requests; case management = `cases` w/ caseworker, stages, visit notes (sensitive class). CVA = cash/voucher disbursement records (amount, channel, status) — track only, no payment rails. Debris = volume estimates per zone → removal tasks. Rebuild tracker = structure → damage grade → permit → repair status. Donor pledges vs received vs distributed ledger. Lessons-learned = tagged findings feeding the cross-incident memory (Sci-Fi).
> **Deps:** Damage Assessment; Logistics; Requests For Help.

- [x] Household needs registry — `seeded from damage+requests`
- [x] Recovery case management — `caseworker, stages, visits`
- [x] Caseworker assignment + load view
- [x] Cash and voucher assistance tracking — `CVA keyword, track-only`
- [x] Relief distribution ledger — `who received what, dedup`
- [x] Debris volume estimation — `per zone, m³`
- [x] Debris removal tasking — `feeds Task system`
- [x] Temporary housing tracker
- [x] Rebuild permit workflow
- [x] Structure repair status tracker — `grade → permit → done`
- [x] Livelihood restoration tracking — `crops, shops, boats`
- [x] Donor pledge tracker — `pledged vs received vs distributed`
- [x] Grant utilization reports
- [x] Long-term recovery dashboard — `months timescale`
- [x] Recovery milestone timeline
- [x] Lessons-learned registry — `tagged findings → memory graph`
- [x] Anniversary review reminders — `cron + memo draft`

## Finance And Cost Tracking *(new section)*
> **Build:** `cost_codes` (incident-scoped chart) + `cost_entries` (code, amount, currency, source: time/equipment/purchase/contract). Time capture from ICS-214 entries × `rate_cards` (role hourly); equipment hours × equipment rates. FEMA PA categories (A–G) as a tagging dimension for reimbursement-shaped exports. Budget caps = soft alerts at thresholds. Multi-currency = store minor units + currency, daily rate snapshot table for rollups. Exports → CSV/XLSX via Reports.
> **Deps:** Logistics; Field Responder (214); Reports.

- [x] Incident cost codes — `chart per incident`
- [x] Cost entry ledger — `time/equipment/purchase/contract`
- [x] Personnel time capture — `from ICS-214 × rate cards`
- [x] Role rate cards
- [x] Equipment usage rates — `hourly/daily per asset class`
- [x] Purchase and contract logging
- [x] FEMA reimbursement categories — `PA cat A–G tagging`
- [x] Budget caps and alerts — `soft thresholds`
- [x] Burn-rate dashboard — `cost over time vs budget`
- [x] Multi-currency support — `minor units + rate snapshots`
- [x] Donor-fund allocation tracking — `fund → cost code mapping`
- [x] Cost summary report export — `CSV/XLSX`
- [x] Claim-ready documentation packet — `costs + evidence bundle`

## Observability QA And Testing *(new section)*
> **Build:** Structured JSON logs w/ request_id (crypto.randomUUID, propagated header) + org/incident ids; ship via Workers Logpush or tail → Baselime/Axiom (OTel-ish). Errors → Sentry `toucan-js`. Metrics = Workers Analytics Engine writes (route, status, ms) + dashboards. Tests: vitest + Miniflare (`@cloudflare/vitest-pool-workers`) for unit/integration vs real D1/DO bindings; Playwright e2e on preview deploys; k6 load on hot routes (ingest, map vectors); axe-core in CI for a11y; Percy/screenshot diff for map regressions. Chaos drill = scripted feed outage + DLQ flood in staging.
> **Deps:** parallel to all phases; wire from P0.

- [x] Structured JSON logging — `request_id propagation`
- [x] Request ID middleware
- [x] Log shipping — `Logpush → Baselime/Axiom`
- [x] Error tracking — `Sentry toucan-js`
- [x] Metrics via Analytics Engine — `route latency/status`
- [x] SLO dashboards — `p95 latency, error rate`
- [x] Alerting on error budget burn
- [x] Queue depth + DLQ alerts
- [x] Feed staleness alerts — `last_success_at > threshold`
- [x] Unit tests — `vitest`
- [x] Integration tests on Workers runtime — `vitest-pool-workers + Miniflare`
- [x] E2E tests — `Playwright vs preview deploys`
- [x] Load tests — `k6 on ingest + map routes`
- [x] Accessibility tests in CI — `axe-core`
- [x] Visual regression tests — `screenshot diff on map/panels`
- [x] Seed-based deterministic test fixtures
- [x] Chaos drill scripts — `feed outage, DLQ flood in staging`
- [x] Synthetic uptime probes — `external ping on public routes`

## Deployment And Infrastructure *(new section)*
> **Build:** wrangler environments (dev/staging/prod) + GitHub Actions: typecheck → test → deploy preview per PR (workers.dev or versioned) → promote. Migrations = drizzle-kit generate, applied via gated CI step (`wrangler d1 migrations apply`), never auto on deploy to prod without approval. Backups = nightly Workflow dumps D1 tables → R2 (also rely on D1 Time Travel); restore runbook doc + tested script. Gradual deploy = Workers gradual rollout %; tenant custom domains via CF for SaaS. IaC optional: terraform cloudflare provider for buckets/queues/DNS.
> **Deps:** P0 onward; CI before features.

- [x] Environment setup — `wrangler env dev/staging/prod`
- [x] CI pipeline — `typecheck → test → deploy`
- [x] Preview deploys per PR
- [x] Gated D1 migrations — `drizzle-kit + manual approve to prod`
- [x] Migration rollback notes — `down scripts where possible`
- [x] Nightly D1 → R2 backup — `Workflow dump`
- [x] D1 Time Travel restore runbook — `tested script`
- [x] R2 lifecycle rules — `tmp uploads expiry`
- [x] Gradual rollout deploys — `percentage-based`
- [x] Instant rollback procedure — `previous version pin`
- [x] Tenant custom domains — `CF for SaaS keyword`
- [x] Smart Placement tuning — `for chatty D1 routes`
- [x] Secrets management per env — `wrangler secret / Secrets Store`
- [x] Infrastructure as code — `terraform cloudflare provider`
- [x] Cost monitoring — `Workers/D1/R2 usage dashboards`
- [x] Status page for the platform itself — `public uptime page`

## Accessibility And Localization *(new section)*
> **Build:** WCAG 2.2 AA as the bar: semantic HTML + ARIA on panels, full keyboard paths (dnd-kit has keyboard sensors), focus management in modals, skip links. Map fallbacks: every map view has a table/list twin. Color = colorblind-safe palettes + never color-only status (icon+text dual coding). i18n = i18next w/ ICU messages; locale files in R2/KV; AI translation drafts → translation review queue (human approve) → glossary lock for fixed terms (place names, "evacuate"). RTL via logical CSS properties; Noto fonts incl. Indic scripts. Plain-language mode = alternate string set, short sentences. TTS on public alerts via Web Speech.
> **Deps:** Core Platform; Communications; runs through every phase.

- [x] WCAG 2.2 AA conformance — `audit checklist + axe CI`
- [x] Full keyboard navigation — `incl. board drag via dnd-kit keyboard`
- [x] Screen reader optimized panels — `ARIA live regions for alerts`
- [x] Focus management + skip links
- [x] Map alternative views — `table twin for every map`
- [x] High-contrast theme
- [x] Reduced motion mode — `prefers-reduced-motion`
- [x] Dyslexia-friendly font option
- [x] Large-touch-target field mode — `gloves keyword`
- [x] Colorblind-safe palettes — `dual coding icon+text`
- [x] Plain-language mode — `alternate string set`
- [x] Text-to-speech for public alerts — `Web Speech API`
- [x] i18n framework — `i18next + ICU messages`
- [x] Locale file management — `KV/R2 backed`
- [x] AI translation draft pipeline — `draft → human review queue`
- [x] Translation review queue — `per-string approve`
- [x] Glossary term locking — `fixed translations for key terms`
- [x] RTL layout support — `CSS logical properties`
- [x] Indic script font support — `Noto fonts`
- [x] Per-user language preference
- [x] Per-incident default language
- [x] Localized number/date/units formatting — `Intl APIs`
