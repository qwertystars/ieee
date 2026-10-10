"""UTC epoch millisecond time utilities.

All timestamps in the platform are stored as UTC epoch milliseconds (BigInteger).
ISO 8601 strings are only used at API boundaries.
"""

import datetime as _dt
import time as _time


def now_ms() -> int:
    """Current UTC time as epoch milliseconds."""
    return int(_time.time() * 1000)


def from_iso(iso_string: str) -> int:
    """Parse an ISO 8601 string to epoch milliseconds.

    Accepts trailing 'Z' or an explicit offset. Naive datetimes are assumed UTC.
    """
    s = iso_string.strip()
    # Python's fromisoformat (pre-3.11) does not accept a trailing 'Z'.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = _dt.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.UTC)
    return int(dt.timestamp() * 1000)


def to_iso(epoch_ms: int) -> str:
    """Convert epoch milliseconds to an ISO 8601 UTC string with millisecond precision."""
    seconds, ms = divmod(int(epoch_ms), 1000)
    dt = _dt.datetime.fromtimestamp(seconds, tz=_dt.UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{ms:03d}Z"


__all__ = ["from_iso", "now_ms", "to_iso"]
