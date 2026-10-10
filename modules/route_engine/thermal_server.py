"""
================================================================================
 ResQnet - Thermal Detection FastAPI Server
================================================================================
 Receives THERMAL_DETECTION payloads from the drone CV pipeline and maintains
 a live registry of confirmed heat signatures (survivor candidates).

 Run:
     uvicorn thermal_server:app --host 0.0.0.0 --port 8765 --reload
================================================================================
"""

from __future__ import annotations

import time
from collections import deque
from typing import List, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────────────────────

class HazardPayload(BaseModel):
    """Schema for incoming thermal detection events."""
    type: Literal["THERMAL_DETECTION"] = "THERMAL_DETECTION"
    coords: List[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Normalised [X, Y] in range [0.0, 1.0] within the drone FOV"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Lock confidence 0-1")
    radius: float     = Field(..., ge=0.0,          description="Estimated contour radius in pixels")


class HazardRecord(HazardPayload):
    """Persisted record with server-side metadata."""
    id:         int
    timestamp:  float
    server_ms:  int   # milliseconds since server start


# ──────────────────────────────────────────────────────────────────────────────
# Application
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ResQnet Thermal Intelligence API",
    description="Receives thermal heat-signature locks from the drone CV pipeline.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store (last 500 events, capped)
_START_TIME   = time.time()
_event_log: deque[HazardRecord] = deque(maxlen=500)
_id_counter   = 0


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "service": "ResQnet Thermal Intelligence API",
        "uptime_s": round(time.time() - _START_TIME, 1),
        "events_logged": len(_event_log),
    }


@app.post("/api/hazard", status_code=201, tags=["Thermal"])
def receive_hazard(payload: HazardPayload) -> HazardRecord:
    """
    Accept a thermal detection lock from the drone CV pipeline.

    - **type**: Must be "THERMAL_DETECTION"
    - **coords**: Normalised [X, Y] ∈ [0.0, 1.0]
    - **confidence**: Blob stability score over the last 5 frames (0–1)
    - **radius**: Contour radius in source pixels
    """
    global _id_counter
    _id_counter += 1

    record = HazardRecord(
        **payload.model_dump(),
        id=_id_counter,
        timestamp=time.time(),
        server_ms=int((time.time() - _START_TIME) * 1000),
    )
    _event_log.append(record)

    print(
        f"[LOCK #{record.id}] "
        f"coords=({record.coords[0]:.3f}, {record.coords[1]:.3f})  "
        f"conf={record.confidence:.2f}  r={record.radius:.1f}px"
    )
    return record


@app.get("/api/hazard", tags=["Thermal"])
def list_hazards(limit: int = 50) -> List[HazardRecord]:
    """Return the most recent `limit` thermal detection events."""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be 1–500")
    recent = list(_event_log)[-limit:]
    return list(reversed(recent))


@app.delete("/api/hazard", tags=["Thermal"])
def clear_hazards():
    """Flush the in-memory event log (admin use)."""
    count = len(_event_log)
    _event_log.clear()
    return {"cleared": count}


# ──────────────────────────────────────────────────────────────────────────────
# Entry point (for direct execution)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("thermal_server:app", host="0.0.0.0", port=8765, reload=True)
