"""Provenance & auditability — hash-chained decision provenance (T49).

For every recommendation, preserves 10 fields: input observation IDs, data
versions, model versions, optimization parameters, scenario set, constraints,
generated alternatives, operator decision, override reason, execution outcome.
Each entry is hash-chained per recommendation_id (same pattern as T3's audit
log — sha256(prev_hash + canonical_json(payload))).

Provides ``ProvenanceChain`` class + ``GET /api/decisions/{id}/provenance``.
Must NOT use blockchain — hash-chained append-only log is sufficient.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.provenance_types import (
    REQUIRED_FIELDS,
    DecisionProvenance,
    ProvenanceInput,
)
from app.db import SessionLocal
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid

# ── Hash-chain helpers (same pattern as T3's audit.py) ──────────────────────


def _canonical_payload(
    recommendation_id: str,
    fields: dict,
    ts: int,
) -> str:
    """Canonical JSON serialization of the provenance payload.

    ``sort_keys=True`` guarantees byte-stable hashing regardless of dict order.
    ``default=str`` covers any non-JSON-native values (datetimes, enums, etc.).
    """
    payload = {"recommendation_id": recommendation_id, "ts": ts}
    payload.update(fields)
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def _compute_hash(prev_hash: str, payload: str) -> str:
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


# ── ProvenanceChain ──────────────────────────────────────────────────────────


class ProvenanceChain:
    """Hash-chained provenance log scoped per recommendation_id.

    Each call to ``record_decision`` appends a new entry linked to the previous
    entry for the same recommendation_id. ``verify_chain`` recomputes hashes
    and reports the first mismatch (or True if intact).
    """

    @staticmethod
    def record_decision(
        db: Session,
        org_id: str,
        recommendation_id: str,
        provenance: ProvenanceInput,
    ) -> DecisionProvenance:
        """Append a provenance entry for a recommendation.

        All 10 fields are required (validated by ``ProvenanceInput``).
        Returns the created entry with its hash-chain fields populated.
        """
        fields = {f: getattr(provenance, f) for f in REQUIRED_FIELDS}

        # Look up the last entry's hash for this recommendation_id.
        last = db.execute(
            select(DecisionProvenance.hash)
            .where(
                DecisionProvenance.org_id == org_id,
                DecisionProvenance.recommendation_id == recommendation_id,
            )
            .order_by(DecisionProvenance.ts.desc(), DecisionProvenance.id.desc())
            .limit(1)
        ).first()
        prev_hash = last[0] if last else ""

        ts = now_ms()
        payload = _canonical_payload(recommendation_id, fields, ts)
        h = _compute_hash(prev_hash, payload)

        entry = DecisionProvenance(
            id=generate_ulid(),
            org_id=org_id,
            recommendation_id=recommendation_id,
            **fields,
            ts=ts,
            prev_hash=prev_hash,
            hash=h,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    @staticmethod
    def get_provenance(
        db: Session,
        org_id: str,
        recommendation_id: str,
    ) -> list[DecisionProvenance]:
        """Return the full provenance chain for a recommendation (oldest first)."""
        rows = db.execute(
            select(DecisionProvenance)
            .where(
                DecisionProvenance.org_id == org_id,
                DecisionProvenance.recommendation_id == recommendation_id,
            )
            .order_by(DecisionProvenance.ts, DecisionProvenance.id)
        ).scalars().all()
        return list(rows)

    @staticmethod
    def verify_chain(
        db: Session,
        org_id: str,
        recommendation_id: str,
    ) -> bool | int:
        """Verify the hash chain for a recommendation.

        Returns True if every entry's hash matches the recomputed value.
        Returns the 0-based index of the first mismatched entry otherwise.
        """
        rows = ProvenanceChain.get_provenance(db, org_id, recommendation_id)
        prev_hash = ""
        for i, entry in enumerate(rows):
            fields = {f: getattr(entry, f) for f in REQUIRED_FIELDS}
            payload = _canonical_payload(entry.recommendation_id, fields, entry.ts)
            expected = _compute_hash(prev_hash, payload)
            if entry.hash != expected:
                return i
            prev_hash = entry.hash
        return True


# ── FastAPI router — GET /api/decisions/{id}/provenance ──────────────────────


router = APIRouter(prefix="/decisions", tags=["provenance"])


@router.get("/{recommendation_id}/provenance")
async def get_provenance_endpoint(
    recommendation_id: str,
    request: Request,
) -> dict:
    """Return the full provenance chain for a recommendation.

    The chain includes all 10 provenance fields per entry plus hash-chain
    integrity info (prev_hash, hash) and a verification result.
    """
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="org_id required")

    db = SessionLocal()
    try:
        rows = ProvenanceChain.get_provenance(db, org_id, recommendation_id)
        if not rows:
            raise HTTPException(status_code=404, detail="provenance not found")

        verified = ProvenanceChain.verify_chain(db, org_id, recommendation_id)
        return {
            "recommendation_id": recommendation_id,
            "entries": [
                {
                    "id": e.id,
                    "ts": e.ts,
                    "prev_hash": e.prev_hash,
                    "hash": e.hash,
                    **{f: getattr(e, f) for f in REQUIRED_FIELDS},
                }
                for e in rows
            ],
            "verified": verified is True,
        }
    finally:
        db.close()


__all__ = ["ProvenanceChain", "router"]
