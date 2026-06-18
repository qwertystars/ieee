"""Aggregate API router (DESIGN §2 boot contract).

Includes every feature router from ``app/api/routes/*.py``. Feature workers add
endpoints to their own route module — they MUST NOT edit this file or main.py.
This router is mounted under ``/api`` by app/main.py.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    areas,
    audit,
    dashboard,
    datasources,
    events,
    observations,
    recommendations,
    reports,
    roads,
    shelters,
    tasks,
    teams,
)

api_router = APIRouter()

api_router.include_router(events.router)
api_router.include_router(datasources.router)
api_router.include_router(observations.router)
api_router.include_router(reports.router)
api_router.include_router(areas.router)
api_router.include_router(recommendations.router)
api_router.include_router(tasks.router)
api_router.include_router(shelters.router)
api_router.include_router(roads.router)
api_router.include_router(teams.router)
api_router.include_router(dashboard.router)
api_router.include_router(audit.router)
