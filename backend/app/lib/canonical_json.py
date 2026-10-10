"""RFC 8785-compatible canonical JSON bytes used by signed contracts."""

from __future__ import annotations

import enum
import json
import math
from collections.abc import Mapping, Sequence
from typing import TypeAlias

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


def _canonical_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("non-finite numbers are not valid canonical JSON")
    if value == 0:
        return "0"
    negative = value < 0
    text = repr(abs(value)).lower()
    mantissa, separator, exponent_text = text.partition("e")
    digits = mantissa.replace(".", "").lstrip("0") or "0"
    fractional_digits = len(mantissa.partition(".")[2])
    power = int(exponent_text) - fractional_digits if separator else -fractional_digits
    absolute = abs(value)
    if 1e-6 <= absolute < 1e21:
        if power >= 0:
            rendered = digits + ("0" * power)
        else:
            position = len(digits) + power
            rendered = (
                digits[:position] + "." + digits[position:]
                if position > 0
                else "0." + ("0" * -position) + digits
            )
        rendered = rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
    else:
        exponent = power + len(digits) - 1
        fraction = digits[1:].rstrip("0")
        rendered = digits[0] + (("." + fraction) if fraction else "")
        rendered += f"e{exponent:+d}"
    return ("-" if negative else "") + rendered


def _canonical(value: JSONValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        pairs = sorted(value.items(), key=lambda item: str(item[0]).encode("utf-16-be"))
        return "{" + ",".join(
            f"{_canonical(str(key))}:{_canonical(item)}" for key, item in pairs
        ) + "}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, enum.Enum):
        return _canonical(value.value)
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: JSONValue) -> bytes:
    """Serialize a JSON-compatible value into deterministic UTF-8 bytes."""
    return _canonical(value).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    """Return the SHA-256 digest of bytes as lowercase hexadecimal."""
    import hashlib

    return hashlib.sha256(value).hexdigest()


__all__ = ["JSONValue", "canonical_json_bytes", "sha256_hex"]
