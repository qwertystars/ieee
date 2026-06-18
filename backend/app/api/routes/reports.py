from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from app.demo_data import REPORTS, add_report, require_event, situation_report_text

router = APIRouter(tags=["reports"])


@router.get("/events/{event_id}/reports")
def list_reports(event_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    require_event(event_id)
    return REPORTS[offset : offset + limit]


@router.post("/events/{event_id}/reports", status_code=201)
def create_report(event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_event(event_id)
    return add_report(payload)


@router.get("/reports/{report_id}")
def get_report(report_id: str) -> dict[str, Any]:
    for report in REPORTS:
        if report["id"] == report_id:
            return report
    from fastapi import HTTPException, status

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")


@router.post("/events/{event_id}/situation-report")
def create_situation_report(event_id: str, payload: dict[str, Any]) -> Response:
    require_event(event_id)
    return Response(content=situation_report_text(), media_type="text/plain")
