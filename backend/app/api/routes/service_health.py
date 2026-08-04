from __future__ import annotations

import socket
from urllib.parse import urlparse

from fastapi import APIRouter
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from typing_extensions import TypedDict

from app.config import settings
from app.lib.observability_metrics import record_dependency

router = APIRouter(tags=["health"])


class ServiceStatus(TypedDict):
    configured: bool
    status: str


class HealthResponse(TypedDict):
    ok: bool
    status: str
    dependency_health: str
    services: dict[str, ServiceStatus]
    environment: str


class DeepHealthResponse(TypedDict):
    ok: bool
    status: str
    checks: dict[str, bool]
    dependency_status: dict[str, str]
    unknown_dependencies: list[str]


def _configured(value: str | None) -> bool:
    return bool(value and value.strip())


def _tcp_probe(endpoint: str) -> bool:
    parsed = urlparse(endpoint if "://" in endpoint else f"tcp://{endpoint}")
    if parsed.hostname is None:
        return False
    port = parsed.port or 0
    if port <= 0:
        return False
    try:
        with socket.create_connection((parsed.hostname, port), timeout=3):
            return True
    except OSError:
        return False


def _dependency_status(configured: bool, reachable: bool | None) -> str:
    if not configured:
        return "configured"
    if reachable is None:
        return "unknown"
    return "reachable" if reachable else "degraded"


@router.get("/healthz")
async def healthz() -> HealthResponse:
    configured = {
        "database": _configured(settings.DATABASE_URL),
        "redis": _configured(settings.REDIS_URL),
        "redpanda": _configured(settings.REDPANDA_BOOTSTRAP_SERVERS),
        "minio": _configured(settings.MINIO_ENDPOINT),
        "ollama": _configured(settings.OLLAMA_BASE_URL),
    }
    services: dict[str, ServiceStatus] = {
        name: {"configured": value, "status": _dependency_status(value, None)}
        for name, value in configured.items()
    }
    for name, is_configured in configured.items():
        record_dependency(name, "unknown" if is_configured else "configured")
    return {
        "ok": True,
        "status": "live",
        "dependency_health": "unknown",
        "services": services,
        "environment": settings.ENVIRONMENT,
    }


def _deep_checks() -> dict[str, bool]:
    checks: dict[str, bool] = {}
    try:
        from app.db import engine

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = True
    except SQLAlchemyError:
        checks["database"] = False

    try:
        import redis

        redis_client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        checks["redis"] = bool(redis_client.ping())
    except RedisError:
        checks["redis"] = False

    checks["redpanda"] = _tcp_probe(settings.REDPANDA_BOOTSTRAP_SERVERS)
    try:
        from minio import Minio

        minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
        minio_client.list_buckets()
        checks["minio"] = True
    except (OSError, RuntimeError, ValueError):
        checks["minio"] = False
    return checks


@router.get("/healthz/deep")
async def healthz_deep() -> DeepHealthResponse:
    checks = _deep_checks()
    statuses = {
        name: _dependency_status(True, reachable)
        for name, reachable in checks.items()
    }
    for name, state in statuses.items():
        record_dependency(name, state)
    all_ok = all(checks.values())
    return {
        "ok": all_ok,
        "status": "reachable" if all_ok else "degraded",
        "checks": checks,
        "dependency_status": statuses,
        "unknown_dependencies": [name for name, state in statuses.items() if state == "unknown"],
    }


__all__ = ["router"]
