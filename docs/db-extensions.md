# Database Extensions Decision (T51 Spike)

**Status:** Decided — all four extensions coexist on PostgreSQL 16.
**Date:** 2026-07-18
**Spike:** T51 (Wave 0) — Validate PostgreSQL + PostGIS + Apache AGE + TimescaleDB coexistence.

## Decision

Build a single custom Docker image (`Dockerfile.db`) based on `postgres:16-bookworm`
that installs **all four** extensions:

| Extension | Version | Source | Purpose |
|---|---|---|---|
| PostGIS | 3.6.4 | PGDG apt (`postgresql-16-postgis-3`) | GeoJSON geometry storage, spatial indexing |
| Apache AGE | 1.6.0 | Built from source (`PG16/v1.6.0-rc0` tag) | Cypher graph queries (knowledge graph) |
| TimescaleDB | 2.28.3 | Timescale apt (`timescaledb-2-postgresql-16`) | Time-series hypertables for sensor history |
| h3 | 4.2.3 | PGDG apt (`postgresql-16-h3`) | H3 hexagonal geospatial indexing in SQL |

**No extension was dropped.** The plan's fallback (drop AGE, use `graph_edges` table +
recursive CTEs) is not needed.

## Why PostgreSQL 16 (not 18)

The plan note said "AGE v1.8.0 requires PG 18.0.0" and "PostGIS 3.4 may not support PG 18."
Both statements are now outdated:

- **Apache AGE** has stable releases for PG 16 (v1.6.0), PG 17 (v1.7.0), and PG 18
  (v1.7.0 stable, v1.8.0-rc0 prerelease). PG 16 has the most battle-tested AGE release.
- **PostGIS 3.5.x** supports PG 12-18 (3.5.5+ supports PG 18 GA; 3.6.4 is in the PGDG
  apt repo for PG 16).
- **TimescaleDB 2.23+** supports PG 15-18.

PG 16 is chosen because:
1. It is the most stable target with the widest extension support matrix.
2. It matches the existing `docker-compose.yml` (`postgis/postgis:16-3.4`).
3. AGE v1.6.0 for PG 16 is the most mature AGE release (v1.7.0/v1.8.0 for PG 18 are
   newer and v1.8.0 is still a release candidate).
4. All three extensions have production-quality packages for PG 16.

## Build approach

The `Dockerfile.db` does three things:

1. **Add apt repositories** — PGDG (for PostGIS, h3, server dev headers) and
   TimescaleDB's packagecloud repo.
2. **Install apt packages** — `postgresql-16-postgis-3`, `postgresql-16-h3`,
   `timescaledb-2-postgresql-16`. These are pre-built and install in seconds.
3. **Build Apache AGE from source** — AGE is not in apt. The Dockerfile clones the
   `PG16/v1.6.0-rc0` tag, runs `make install` against the PG 16 server headers, then
   purges the build toolchain to keep the image lean.

## shared_preload_libraries

The image starts postgres with:

```
postgres -c shared_preload_libraries=timescaledb,age
```

- **TimescaleDB** requires preloading for its background worker (hypertable retention,
  continuous aggregates).
- **Apache AGE** requires preloading so its `cypher()` function handler is registered
  in every session. Without it, `cypher()` fails with
  `ERROR: unhandled cypher(cstring) function call`. The alternative is
  `LOAD 'age';` in every session, which is fragile.

## Usage notes for application code

### AGE (cypher queries)

AGE installs all functions in the `ag_catalog` schema. Application code must either:

- Set `search_path = ag_catalog, public` per session, or
- Schema-qualify calls: `ag_catalog.cypher(...)`, and use `ag_catalog.agtype` for
  the return column type.

Example:

```sql
SET search_path = ag_catalog, public;
SELECT create_graph('knowledge_graph');
SELECT * FROM cypher('knowledge_graph', $$
  CREATE (n:Incident {id: 'ULID-HERE', type: 'flood'})
  RETURN n
$$) AS (n ag_catalog.agtype);
```

### h3 (H3 indexing)

The h3-pg extension v4.x takes a PostgreSQL `point` type, **not** separate lat/lng
arguments:

```sql
-- Correct: point type
SELECT h3_lat_lng_to_cell(point '(40.7484, -73.9857)', 9);
-- Returns: 89f05ab6adbffff

-- Wrong: separate args (function does not exist)
SELECT h3_lat_lng_to_cell(40.7484, -73.9857, 9);  -- ERROR
```

`h3_lat_lng_to_cell` is deprecated in favor of `h3_latlng_to_cell` (same signature,
no underscore) — both work in v4.2.3. Application code should use `h3_latlng_to_cell`.

To convert a PostGIS geometry to an h3 cell, cast through `point`:

```sql
SELECT h3_latlng_to_cell(ST_AsText(ST_Centroid(geom))::point, 9);
```

### TimescaleDB

Standard hypertable creation works as expected:

```sql
CREATE TABLE sensor_readings (
  ts TIMESTAMPTZ NOT NULL,
  sensor_id TEXT NOT NULL,
  value DOUBLE PRECISION
);
SELECT create_hypertable('sensor_readings', 'ts');
```

## Verification

The image was verified with a full functional test (see
`.omo/evidence/task-0a-resqnet-sage.txt`):

- `docker build -t resqnet-db -f Dockerfile.db .` exits 0.
- All four `CREATE EXTENSION` commands succeed in the same database.
- PostGIS `ST_Point()`, h3 `h3_lat_lng_to_cell()`, TimescaleDB `create_hypertable()`,
  and AGE `create_graph()` + `cypher()` CREATE/MATCH all return correct results.

## Future considerations

- **AGE upgrade path:** If AGE v1.8.0 becomes stable, consider upgrading to PG 18 for
  `shortest_path` / `all_shortest_paths` SRFs and `create_subgraph()` features.
- **h3 deprecation:** Migrate from `h3_lat_lng_to_cell` to `h3_latlng_to_cell` before
  the next major h3-pg release.
- **TimescaleDB columnstore:** PG 18's async I/O improvements would benefit TimescaleDB
  columnstore scans; revisit PG 18 once AGE v1.8.0 is stable.
