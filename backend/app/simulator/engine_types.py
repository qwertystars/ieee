"""Deterministic identifier helpers for the simulation engine."""

import random

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _b32_encode(data: bytes, length: int) -> str:
    num = int.from_bytes(data, "big")
    out: list[str] = []
    for _ in range(length):
        out.append(_CROCKFORD[num & 0x1F])
        num >>= 5
    return "".join(reversed(out))


def deterministic_ulid(rng: random.Random, ts_ms: int) -> str:
    """Same seed and elapsed time produce the same simulation identifiers."""
    return _b32_encode(ts_ms.to_bytes(6, "big"), 10) + _b32_encode(rng.randbytes(10), 16)
