from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

EVENT_ID = "11111111-1111-4111-8111-111111111111"
USER_ID = "22222222-2222-4222-8222-222222222222"
STARTED_AT = "2026-06-03T05:30:00+00:00"
UPDATED_AT = "2026-06-03T06:15:00+00:00"

DEMO_USERS: dict[str, dict[str, str]] = {
    "admin@demo.disaster": {"name": "Admin", "role": "admin"},
    "emergency_manager@demo.disaster": {"name": "Emergency Manager", "role": "emergency_manager"},
    "responder_coordinator@demo.disaster": {"name": "Responder Coordinator", "role": "responder_coordinator"},
    "field_responder@demo.disaster": {"name": "Field Responder", "role": "field_responder"},
    "shelter_manager@demo.disaster": {"name": "Shelter Manager", "role": "shelter_manager"},
    "viewer@demo.disaster": {"name": "Viewer", "role": "viewer"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def point(lon: float, lat: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [lon, lat]}


def line(*points: tuple[float, float]) -> dict[str, Any]:
    return {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in points]}


def polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [[[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]],
    }


def user_payload(email: str) -> dict[str, Any]:
    user = DEMO_USERS.get(email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {
        "id": USER_ID,
        "name": user["name"],
        "email": email,
        "role": user["role"],
        "organization": "Rivertown Emergency Management",
        "phone": None,
        "status": "active",
        "created_at": STARTED_AT,
        "updated_at": UPDATED_AT,
    }


BASE_EVENT: dict[str, Any] = {
    "id": EVENT_ID,
    "name": "Rivertown Urban Flood",
    "type": "flood",
    "status": "active",
    "start_time": STARTED_AT,
    "end_time": None,
    "description": "Simulated urban flooding along Lake Road and the Riverside district.",
    "affected_region": polygon(-80.04, 25.98, -79.96, 26.04),
    "created_by": USER_ID,
    "created_at": STARTED_AT,
    "updated_at": UPDATED_AT,
}

BASE_OBSERVATIONS: list[dict[str, Any]] = [
    {
        "id": "30000000-0000-4000-8000-000000000001",
        "event_id": EVENT_ID,
        "source_id": "30000000-0000-4000-8000-000000000099",
        "observation_type": "flood_extent",
        "geometry": polygon(-80.025, 26.0, -79.99, 26.028),
        "timestamp": "2026-06-03T06:05:00+00:00",
        "value": 0.92,
        "unit": "probability",
        "description": "Satellite-derived flood extent over Riverside and Lake Road.",
        "confidence_score": 0.86,
        "metadata": {"source": "simulated_satellite"},
        "cluster_id": None,
        "created_at": "2026-06-03T06:06:00+00:00",
    }
]

AREA_INPUTS = [
    ("0001", "Riverside Ward", polygon(-80.024, 26.004, -79.998, 26.026), "critical", 86.4, [92, 88, 76, 84, 70, 82, 91], "Rising flood water, trapped-person reports, power loss, and two blocked access roads."),
    ("0002", "Market District", polygon(-80.006, 25.992, -79.982, 26.01), "high", 63.0, [68, 74, 58, 61, 48, 60, 64], "Street flooding is disrupting access to clinics and supply warehouses."),
    ("0003", "North School Zone", polygon(-80.035, 26.018, -80.02, 26.036), "medium", 41.4, [41, 55, 35, 30, 62, 38, 28], "Monitor school access as runoff moves north."),
]

BASE_AREAS: list[dict[str, Any]] = [
    {
        "id": f"40000000-0000-4000-8000-00000000{suffix}",
        "event_id": EVENT_ID,
        "area_name": name,
        "geometry": geom,
        "hazard_score": scores[0],
        "exposure_score": scores[1],
        "access_score": scores[2],
        "infrastructure_score": scores[3],
        "vulnerability_score": scores[4],
        "trend_score": scores[5],
        "report_score": scores[6],
        "overall_priority_score": overall,
        "priority_level": level,
        "summary": summary,
        "components": {"why": summary.split(", ")},
        "updated_at": "2026-06-03T06:12:00+00:00",
    }
    for suffix, name, geom, level, overall, scores, summary in AREA_INPUTS
]

REPORT_INPUTS = [
    ("0001", "citizen", "trapped_person", "Family trapped on second floor near Lake Road.", point(-80.014, 26.016), "critical", "medium", 0.62),
    ("0002", "field_responder", "road_blocked", "Lake Road blocked by flood water at the underpass.", point(-80.011, 26.01), "high", "high", 0.91),
    ("0003", "citizen", "power_outage", "Power outage across Riverside blocks 4 through 8.", point(-80.006, 26.019), "high", "low", 0.48),
    ("0004", "official", "shelter_need", "Riverside Shelter is nearing capacity.", point(-79.986, 26.007), "medium", "high", 0.95),
]

BASE_REPORTS: list[dict[str, Any]] = [
    {
        "id": f"50000000-0000-4000-8000-00000000{suffix}",
        "event_id": EVENT_ID,
        "reporter_type": reporter,
        "report_category": category,
        "description": description,
        "geometry": geom,
        "photo_url": None,
        "urgency": urgency,
        "verification_status": verification,
        "confidence_score": confidence,
        "pii_redacted_text": description,
        "cluster_id": "60000000-0000-4000-8000-000000000001" if category == "trapped_person" else None,
        "created_at": "2026-06-03T06:02:00+00:00",
        "updated_at": "2026-06-03T06:04:00+00:00",
    }
    for suffix, reporter, category, description, geom, urgency, verification, confidence in REPORT_INPUTS
]

SHELTER_INPUTS = [
    ("0001", "Central High Shelter", point(-79.978, 26.016), 1200, 450, "adequate", "adequate", True, True, "open"),
    ("0002", "Riverside Community Center", point(-79.986, 26.007), 700, 665, "low", "adequate", False, True, "open"),
    ("0003", "North Gym Annex", point(-80.032, 26.035), 500, 0, "staged", "staged", False, False, "open"),
]

BASE_SHELTERS: list[dict[str, Any]] = [
    {
        "id": f"70000000-0000-4000-8000-00000000{suffix}",
        "name": name,
        "geometry": geom,
        "total_capacity": total,
        "current_occupancy": occupied,
        "available_capacity": total - occupied,
        "food_status": food,
        "water_status": water,
        "medical_support": medical,
        "accessibility_support": accessible,
        "status": shelter_status,
        "updated_at": "2026-06-03T06:08:00+00:00",
    }
    for suffix, name, geom, total, occupied, food, water, medical, accessible, shelter_status in SHELTER_INPUTS
]

BASE_ROADS = [
    {"id": "80000000-0000-4000-8000-000000000001", "event_id": EVENT_ID, "road_name": "Lake Road", "geometry": line((-80.03, 26.008), (-79.98, 26.008)), "status": "blocked", "reason": "Flooded underpass", "confidence_score": 0.91, "updated_at": "2026-06-03T06:01:00+00:00"},
    {"id": "80000000-0000-4000-8000-000000000002", "event_id": EVENT_ID, "road_name": "Bridge Street", "geometry": line((-80.015, 25.995), (-80.015, 26.03)), "status": "blocked", "reason": "Bridge approach underwater", "confidence_score": 0.84, "updated_at": "2026-06-03T06:04:00+00:00"},
    {"id": "80000000-0000-4000-8000-000000000003", "event_id": EVENT_ID, "road_name": "Main Evacuation Route", "geometry": line((-80.035, 26.032), (-79.974, 26.018)), "status": "open", "reason": "Responder verified", "confidence_score": 0.88, "updated_at": "2026-06-03T06:06:00+00:00"},
]

BASE_TEAMS = [
    {"id": "90000000-0000-4000-8000-000000000001", "name": "Rescue Team Alpha", "team_type": "rescue", "current_location": point(-80.028, 26.023), "status": "en_route", "capacity": 8, "assigned_task_id": "99000000-0000-4000-8000-000000000001", "updated_at": "2026-06-03T06:12:00+00:00"},
    {"id": "90000000-0000-4000-8000-000000000002", "name": "Medical Unit 3", "team_type": "medical", "current_location": point(-79.981, 26.015), "status": "available", "capacity": 4, "assigned_task_id": None, "updated_at": "2026-06-03T06:09:00+00:00"},
]

BASE_TASKS = [
    {"id": "99000000-0000-4000-8000-000000000001", "event_id": EVENT_ID, "recommendation_id": "a0000000-0000-4000-8000-000000000002", "assigned_team_id": "90000000-0000-4000-8000-000000000001", "title": "Rescue trapped residents near Lake Road", "description": "Reach the cluster using Main Evacuation Route and avoid Bridge Street.", "location": point(-80.014, 26.016), "priority": "critical", "status": "assigned", "created_at": "2026-06-03T06:07:00+00:00", "updated_at": "2026-06-03T06:07:00+00:00"}
]

RECOMMENDATION_INPUTS = [
    ("0001", "evacuation", "Evacuate Riverside Ward", "Move exposed residents to Central High Shelter via Main Evacuation Route.", "Flood extent is expanding, 4,800 residents are exposed, and two local roads are blocked.", 0.84, "critical", "draft", None),
    ("0002", "rescue", "Send rescue team to Lake Road cluster", "Dispatch Rescue Team Alpha to the trapped-person report cluster.", "Critical trapped-person report is corroborated by responder road-block data.", 0.88, "critical", "reviewed", "90000000-0000-4000-8000-000000000001"),
    ("0003", "open_shelter", "Open North Gym Annex overflow", "Prepare additional shelter space because Riverside Community Center has 35 spaces left.", "Shelter demand is likely to exceed capacity if Riverside evacuation proceeds.", 0.79, "high", "draft", None),
]

BASE_RECOMMENDATIONS = [
    {"id": f"a0000000-0000-4000-8000-00000000{suffix}", "event_id": EVENT_ID, "area_assessment_id": "40000000-0000-4000-8000-000000000001", "recommendation_type": kind, "title": title, "description": description, "reasoning": reasoning, "supporting_data": {"safe_route": "Main Evacuation Route", "blocked_roads_avoided": ["Lake Road", "Bridge Street"]}, "confidence_score": confidence, "urgency": urgency, "status": rec_status, "assigned_to": assigned_to, "created_at": "2026-06-03T06:12:00+00:00", "updated_at": "2026-06-03T06:12:00+00:00"}
    for suffix, kind, title, description, reasoning, confidence, urgency, rec_status, assigned_to in RECOMMENDATION_INPUTS
]

BASE_ALERTS = [
    {"id": "b0000000-0000-4000-8000-000000000001", "event_id": EVENT_ID, "alert_type": "critical_area_detected", "title": "Critical flooding detected in Riverside Ward", "message": "Rising flood water overlaps high population exposure and blocked roads.", "area": BASE_AREAS[0]["geometry"], "severity": "critical", "recommended_action": "Review evacuation and rescue recommendations.", "confidence_score": 0.86, "acknowledged": False, "created_at": "2026-06-03T06:12:00+00:00"}
]

REPORTS = deepcopy(BASE_REPORTS)
RECOMMENDATIONS = deepcopy(BASE_RECOMMENDATIONS)


def reset_demo_state() -> None:
    REPORTS.clear()
    REPORTS.extend(deepcopy(BASE_REPORTS))
    RECOMMENDATIONS.clear()
    RECOMMENDATIONS.extend(deepcopy(BASE_RECOMMENDATIONS))


def require_event(event_id: str) -> None:
    if event_id != EVENT_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")


def dashboard_summary() -> dict[str, Any]:
    active_statuses = {"draft", "reviewed", "approved", "assigned", "in_progress"}
    return {
        "event_id": EVENT_ID,
        "total_observations": len(BASE_OBSERVATIONS),
        "total_reports": len(REPORTS),
        "unverified_reports": len([report for report in REPORTS if report["verification_status"] != "high"]),
        "critical_areas": len([area for area in BASE_AREAS if area["priority_level"] == "critical"]),
        "high_areas": len([area for area in BASE_AREAS if area["priority_level"] == "high"]),
        "medium_areas": len([area for area in BASE_AREAS if area["priority_level"] == "medium"]),
        "low_areas": len([area for area in BASE_AREAS if area["priority_level"] == "low"]),
        "active_recommendations": len([rec for rec in RECOMMENDATIONS if rec["status"] in active_statuses]),
        "pending_tasks": len([task for task in BASE_TASKS if task["status"] != "completed"]),
        "shelters_open": len([shelter for shelter in BASE_SHELTERS if shelter["status"] == "open"]),
        "shelters_full": len([shelter for shelter in BASE_SHELTERS if shelter["status"] == "full"]),
        "roads_blocked": len([road for road in BASE_ROADS if road["status"] == "blocked"]),
        "teams_deployed": len([team for team in BASE_TEAMS if team["status"] not in {"available", "standby"}]),
        "alerts_active": len([alert for alert in BASE_ALERTS if not alert["acknowledged"]]),
        "last_updated": now_iso(),
    }


def map_layers() -> dict[str, Any]:
    return {"event_id": EVENT_ID, "observations": deepcopy(BASE_OBSERVATIONS), "reports": deepcopy(REPORTS), "areas": deepcopy(BASE_AREAS), "shelters": deepcopy(BASE_SHELTERS), "roads": deepcopy(BASE_ROADS), "teams": deepcopy(BASE_TEAMS)}


def add_report(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("geometry") is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="geometry is required")
    confidence = 0.88 if payload.get("reporter_type") == "field_responder" else 0.45
    verification_status = "high" if payload.get("reporter_type") == "field_responder" else "unverified"
    timestamp = now_iso()
    report = {"id": f"50000000-0000-4000-8000-{len(REPORTS) + 1:012d}", "event_id": EVENT_ID, "reporter_type": payload.get("reporter_type"), "report_category": payload.get("report_category"), "description": payload.get("description"), "geometry": payload["geometry"], "photo_url": payload.get("photo_url"), "urgency": payload.get("urgency", "medium"), "verification_status": verification_status, "confidence_score": confidence, "pii_redacted_text": payload.get("description"), "cluster_id": None, "created_at": timestamp, "updated_at": timestamp}
    REPORTS.append(report)
    return deepcopy(report)


def set_recommendation_status(recommendation_id: str, next_status: str) -> dict[str, Any]:
    for recommendation in RECOMMENDATIONS:
        if recommendation["id"] == recommendation_id:
            recommendation["status"] = next_status
            recommendation["updated_at"] = now_iso()
            return deepcopy(recommendation)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")


def approve_recommendation(recommendation_id: str) -> dict[str, Any]:
    return set_recommendation_status(recommendation_id, "approved")


def dismiss_recommendation(recommendation_id: str) -> dict[str, Any]:
    return set_recommendation_status(recommendation_id, "dismissed")


def situation_report_text() -> str:
    summary = dashboard_summary()
    recommendation_lines = [f"- {str(rec['status']).upper()}: {rec['title']} ({rec['urgency']}, confidence {rec['confidence_score']})" for rec in RECOMMENDATIONS]
    return "\n".join(["Situation Report", f"Event: {BASE_EVENT['name']}", f"Generated: {summary['last_updated']}", f"Reports: {summary['total_reports']} total, {summary['unverified_reports']} not high-confidence", f"Priority: {summary['critical_areas']} critical area, {summary['roads_blocked']} blocked roads", "Recommendations:", *recommendation_lines])
