# Resqnet-Sage Learnings

## T51 — PostgreSQL extension coexistence spike (2026-07-18)

### Outcome
All four extensions (PostGIS, Apache AGE, TimescaleDB, h3) coexist successfully on
PostgreSQL 16 in a single Docker image. No extension was dropped.

### Key findings

1. **The plan's compatibility note was outdated.** The plan said "AGE v1.8.0 requires
   PG 18.0.0" and "PostGIS 3.4 may not support PG 18." In reality:
   - AGE v1.6.0 stable supports PG 16 (tag `PG16/v1.6.0-rc0`).
   - AGE v1.7.0 stable supports PG 17 and PG 18.
   - PostGIS 3.5.x supports PG 12-18 (3.5.5+ supports PG 18 GA).
   - TimescaleDB 2.23+ supports PG 15-18.

2. **AGE must be in `shared_preload_libraries`.** Without it, `cypher()` fails with
   `ERROR: unhandled cypher(cstring) function call`. The `LOAD 'age';` command works
   as a per-session workaround but is fragile. Setting
   `shared_preload_libraries=timescaledb,age` in the Docker CMD is the clean fix.

3. **AGE functions live in `ag_catalog` schema.** Application code must set
   `search_path = ag_catalog, public` or schema-qualify all calls
   (`ag_catalog.cypher()`, `ag_catalog.agtype`).

4. **h3-pg v4.x takes a `point` type, not separate lat/lng args.**
   `h3_lat_lng_to_cell(point '(lat, lng)', resolution)` works.
   `h3_lat_lng_to_cell(40.7, -73.9, 9)` does NOT exist.
   `h3_lat_lng_to_cell` is deprecated in favor of `h3_latlng_to_cell` (same signature).

5. **AGE is not in apt — must build from source.** The build requires
   `postgresql-server-dev-16`, `flex`, `bison`, `build-essential`, `git`. The
   Dockerfile purges these after `make install` to keep the image lean.

6. **PG 16 is the right choice over PG 18.** PG 16 has the most mature AGE release
   (v1.6.0), matches the existing `docker-compose.yml`, and all three extensions have
   production-quality packages for it. PG 18 would work too, but AGE v1.8.0 for PG 18
   is still a release candidate.

### Versions installed
- PostgreSQL 16 (Debian Bookworm base)
- PostGIS 3.6.4 (from PGDG apt)
- Apache AGE 1.6.0 (built from source, `PG16/v1.6.0-rc0` tag)
- TimescaleDB 2.28.3 (from Timescale packagecloud apt)
- h3 4.2.3 (from PGDG apt)

### Files produced
- `Dockerfile.db` — custom PostgreSQL 16 image with all four extensions.
- `docs/db-extensions.md` — decision document with usage notes.
- `.omo/evidence/task-0a-resqnet-sage.txt` — full test output.
