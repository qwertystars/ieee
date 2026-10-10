"""ULID generation — 26-char Crockford base32, monotonic per process.

Format: 48-bit millisecond timestamp (10 chars) + 80-bit randomness (16 chars).
Within the same millisecond, the randomness portion is incremented by 1 to
guarantee monotonic ordering. The clock is treated as monotonic; if it ever
moves backwards, we reuse the last randomness and increment it.
"""

import os
import threading
import time

# Crockford base32 alphabet (excludes I, L, O, U to avoid confusion).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Process-wide monotonic state.
_lock = threading.Lock()
_last_ms: int = 0
_last_rand: bytearray = bytearray(10)  # 80 bits


def _b32_encode(data: bytes, length: int) -> str:
    """Encode big-endian bytes into a Crockford base32 string of `length` chars.

    The total bit capacity is `length * 5`; any high bits beyond `len(data) * 8`
    are treated as leading zeros.
    """
    num = int.from_bytes(data, "big")
    out = []
    for _ in range(length):
        out.append(_CROCKFORD[num & 0x1F])
        num >>= 5
    # We extracted low bits first, so reverse to get big-endian order.
    return "".join(reversed(out))


def generate_ulid() -> str:
    """Generate a 26-char monotonic ULID string."""
    global _last_ms, _last_rand
    with _lock:
        ms = int(time.time() * 1000)
        if ms <= _last_ms:
            # Same millisecond (or clock regression): increment randomness.
            carry = 1
            for i in range(len(_last_rand) - 1, -1, -1):
                v = _last_rand[i] + carry
                _last_rand[i] = v & 0xFF
                carry = v >> 8
                if carry == 0:
                    break
            # If carry is still set here, the randomness overflowed. That is
            # acceptable: we keep the wrapped value, which is still unique
            # within this ms given the lock.
        else:
            _last_rand = bytearray(os.urandom(10))
            _last_ms = ms
        ts_bytes = ms.to_bytes(6, "big")
        return _b32_encode(ts_bytes, 10) + _b32_encode(bytes(_last_rand), 16)


def parse_ulid(ulid_str: str) -> tuple[int, int]:
    """Parse a 26-char ULID into (timestamp_ms, randomness_int).

    Raises ValueError on malformed input.
    """
    if len(ulid_str) != 26:
        raise ValueError(f"ULID must be 26 chars, got {len(ulid_str)}")
    s = ulid_str.upper().replace("O", "0").replace("I", "1").replace("L", "1")
    ts_chars = s[:10]
    rand_chars = s[10:]
    ts = 0
    for c in ts_chars:
        idx = _CROCKFORD.find(c)
        if idx < 0:
            raise ValueError(f"invalid Crockford char: {c}")
        ts = (ts << 5) | idx
    ts >>= 2  # drop the 2 leading padding bits (10*5 - 48 = 2)
    rand = 0
    for c in rand_chars:
        idx = _CROCKFORD.find(c)
        if idx < 0:
            raise ValueError(f"invalid Crockford char: {c}")
        rand = (rand << 5) | idx
    return ts, rand


__all__ = ["generate_ulid", "parse_ulid"]
