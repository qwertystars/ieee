"""Keyword tables and regex patterns for the citizen-report NLP pipeline.

Multilingual keyword maps (English + Hindi romanized + Devanagari) for
urgency and category extraction, plus PII regex patterns and place-name
extraction patterns. Isolated in this module so ``nlp.py`` stays under the
250 pure LOC ceiling.
"""

from __future__ import annotations

import re

# ─── Urgency keywords ───────────────────────────────────────────────────────
# Order matters: critical is checked first, then high, etc. A report
# matching "trapped" (critical) should not be downgraded to medium even if
# it also contains "need" (medium).

URGENCY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "critical": (
        "trapped", "stuck", "drowning", "unconscious", "not breathing",
        "dying", "critical", "sinking", "buried", "collapsed on",
        "phansa", "dub", "meramat", "ghayal",
        "फंसे", "डूब", "मरता", "गंभीर",
    ),
    "high": (
        "urgent", "emergency", "help", "rescue", "bleeding",
        "rising water", "breaking", "trapped in",
        "madad", "bachao", "suraksha", "jaldi",
        "मदद", "बचाओ", "जल्दी",
    ),
    "medium": (
        "need", "stranded", "no food", "no water", "no power",
        "flood rising", "cut off", "shelter",
        "rahat", "samagri", "bhojan", "pani",
        "राहत", "सामग्री", "भोजन", "पानी",
    ),
    "low": (
        "fine", "safe", "minor", "small", "okay", "all good",
        "thik", "surakshit", "chot",
        "ठीक", "सुरक्षित",
    ),
}

# ─── Category keywords ───────────────────────────────────────────────────────

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "trapped_person": ("trapped", "stuck", "phansa", "फंसे", "buried"),
    "missing_person": ("missing", "lost", "gone", "kho", "खो"),
    "medical_emergency": ("injured", "bleeding", "unconscious", "medical", "ghayal", "अस्पताल"),
    "flooding": ("flood", "water rising", "drowning", "dub", "बाढ़", "पानी"),
    "structural_collapse": ("collapsed", "collapse", "building fell", "dhara", "गिर"),
    "fire_electrical": ("fire", "smoke", "electrical", "short circuit", "aag", "आग"),
    "blocked_route": ("blocked", "road closed", "impassable", "band", "बंद"),
    "shelter_request": ("shelter", "need place", "roof", "ashray", "आश्रय"),
    "food_water_medication": ("food", "water", "medicine", "medication", "khana", "pani", "दवा"),
    "infrastructure_outage": ("power", "no electricity", "outage", "bijli", "बिजली"),
    "rescue_completed": ("rescued", "saved", "safe now", "bacha", "बचाया"),
}

# ─── PII regex patterns ──────────────────────────────────────────────────────
# Indian phone (10 digits starting 6-9, optional +91 prefix), email,
# Aadhaar (12 digits, optionally space-grouped), and a person-name heuristic
# (two consecutive capitalized words not at sentence start).

PHONE_RE = re.compile(r"(?:\+91[\-\s]?)?[6-9]\d{9}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
NAME_RE = re.compile(r"(?<![\.\!\?]\s)\b([A-Z][a-z]+)\s([A-Z][a-z]+)\b")

# ─── Place-name extraction ──────────────────────────────────────────────────

PLACE_PATTERN_RE = re.compile(
    r"(?:near|at|in|around|from|opp\.?)\s+(?:the\s+)?"
    r"([A-Z][a-zA-Z\s]{2,40}|[a-z][a-z\s]{2,40})",
)
PLACE_SUFFIXES = (
    "market", "school", "hospital", "bridge", "station", "nagar",
    "colony", "road", "street", "marg", "chowk", "mandir", "masjid",
    "bus stop", "railway", "airport",
)

# Vague location qualifiers — when present, the geolocation MUST be a
# distribution or uncertainty polygon, never an exact point.
VAGUE_QUALIFIERS = ("near", "around", "close to", "somewhere", "about", "roughly")

# Exact coordinate pattern (lat,lng) — only this justifies an exact point.
COORD_RE = re.compile(r"\b(-?\d{1,3}\.\d{3,8})\s*,\s*(-?\d{1,3}\.\d{3,8})\b")


__all__ = [
    "AADHAAR_RE",
    "CATEGORY_KEYWORDS",
    "COORD_RE",
    "EMAIL_RE",
    "NAME_RE",
    "PHONE_RE",
    "PLACE_PATTERN_RE",
    "PLACE_SUFFIXES",
    "URGENCY_KEYWORDS",
    "VAGUE_QUALIFIERS",
]
