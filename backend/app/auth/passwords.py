"""Password hashing using bcrypt directly.

Uses the `bcrypt` package directly instead of passlib to avoid a known
compatibility issue between passlib and bcrypt 4.x (passlib's internal
detect_wrap_bug test hashes a >72-byte string, which bcrypt 4.x rejects).
"""

import bcrypt


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the password."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True if the password matches the bcrypt hash."""
    return bcrypt.checkpw(
        password.encode("utf-8"), hashed.encode("utf-8")
    )
