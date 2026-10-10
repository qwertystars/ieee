"""Seed data package — fixtures and demo scenario populator for Rivertown.

Run `python -m app.seed.seed_demo` to populate the DB with a cyclone-flood
scenario: 1 incident, 5 zones, 20 roads, 3 shelters, 2 hospitals, 10 buildings,
5 responders, 3 vehicles, 50 observations, 5 hypotheses, 3 scenarios.

All fixtures are local files under ``app/seed/fixtures/`` — no internet required.
The seed is idempotent: running twice produces the same row counts (deterministic
IDs via SHA-256 of a stable key, delete-then-insert per org+incident scope).
"""
