"""Deterministic ID generation for seed data.

Uses a fixed timestamp prefix + SHA-256 hash of a key string to produce
26-char Crockford base32 IDs that look like ULIDs but are fully deterministic.
This ensures idempotency: running the seed twice produces the same IDs, so
delete-then-insert yields the same row count.
"""

import hashlib

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SEED_TS_MS = 1753000000000  # Fixed: 2026-07-20T00:00:00Z


def _b32_encode(data: bytes, length: int) -> str:
    """Encode big-endian bytes into Crockford base32 of `length` chars."""
    num = int.from_bytes(data, "big")
    out = []
    for _ in range(length):
        out.append(_CROCKFORD[num & 0x1F])
        num >>= 5
    return "".join(reversed(out))


def seed_id(key: str) -> str:
    """Generate a deterministic 26-char ULID-like ID from a key string.

    The first 10 chars encode a fixed timestamp; the last 16 chars are derived
    from SHA-256(key). Same key always produces the same ID.
    """
    ts_bytes = _SEED_TS_MS.to_bytes(6, "big")
    ts_str = _b32_encode(ts_bytes, 10)
    rand_bytes = hashlib.sha256(key.encode("utf-8")).digest()[:10]
    rand_str = _b32_encode(rand_bytes, 16)
    return ts_str + rand_str


# Stable incident/org identifiers for the demo scenario.
# ORG_ID matches auth/seed.py DEMO_ORG_ID so demo users and demo data share org.
ORG_ID = "org_demo"
INCIDENT_ID = seed_id("rivertown_cyclone_flood_2026")
INCIDENT_NAME = "Rivertown Cyclone-Flood 2026"

RESCUE_BALL_DEVICE_1_ID = seed_id("sensor:rescue_ball_1")
RESCUE_BALL_DEVICE_2_ID = seed_id("sensor:rescue_ball_2")

ALERT_ID = seed_id("alert:trapped_person_ward_2")
RECOMMENDATION_ID = seed_id("rec:rescue_operation_ward_2")
TASK_ID = seed_id("task:rescue_trapped_person")
