"""FastAPI application entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: seed users + start Kafka producer. Shutdown: stop producer."""
    # 0. Store the main event loop for sync->async broadcast scheduling.
    app.state.event_loop = asyncio.get_running_loop()

    # 1. Seed demo users (users table is created by Alembic migration 0002b).
    from app.auth.seed import seed_demo_users
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        count = seed_demo_users(db)
        if count > 0:
            logger.info("Seeded %d demo users", count)
    finally:
        db.close()

    # 2. Start Redpanda/Kafka producer (best-effort — don't crash if down).
    producer = None
    try:
        from aiokafka import AIOKafkaProducer

        producer = AIOKafkaProducer(
            bootstrap_servers=settings.REDPANDA_BOOTSTRAP_SERVERS
        )
        await producer.start()
        app.state.kafka_producer = producer
        logger.info("Kafka producer started")
    except Exception as exc:
        logger.warning("Kafka producer failed to start (non-fatal): %s", exc)
        app.state.kafka_producer = None

    yield

    # Shutdown: stop Kafka producer (best-effort).
    if producer is not None:
        try:
            await producer.stop()
            logger.info("Kafka producer stopped")
        except Exception as exc:
            logger.warning("Kafka producer failed to stop: %s", exc)


app = FastAPI(
    title="ResQNet-SAGE",
    description="Disaster Situational Awareness & Response Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (added first → innermost user middleware).
if settings.CORS_ORIGINS == "*":
    logger.warning(
        "CORS_ORIGINS is '*' — allow_credentials disabled. "
        "Set CORS_ORIGINS to specific origins for credential support."
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Middleware order (last added = outermost = runs first on request):
# RequestID → OrgContext → CORS → router
from app.middleware.error_handler import register_error_handlers
from app.middleware.org_context import OrgContextMiddleware
from app.middleware.request_id import RequestIDMiddleware

app.add_middleware(OrgContextMiddleware)
app.add_middleware(RequestIDMiddleware)

# Register global error handlers.
register_error_handlers(app)

# ── Telemetry (OpenTelemetry traces + Prometheus metrics) ───────────────────
from app.lib.telemetry import setup_telemetry

setup_telemetry(app)


# ── Health checks ───────────────────────────────────────────────────────────


@app.get("/healthz")
async def healthz() -> dict:
    """Shallow health check — returns configured service names without URLs."""
    return {
        "ok": True,
        "services": {
            "database": "configured",
            "redis": "configured",
            "redpanda": "configured",
            "minio": "configured",
            "ollama": "configured",
        },
        "environment": settings.ENVIRONMENT,
    }


@app.get("/healthz/deep")
async def healthz_deep() -> dict:
    """Deep health check — tests connectivity to PostgreSQL, Redis, Redpanda, MinIO."""
    checks: dict[str, bool] = {}

    # PostgreSQL
    try:
        from app.db import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    # Redis
    try:
        import redis

        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    # Redpanda (TCP connect check)
    try:
        import socket

        host, port = settings.REDPANDA_BOOTSTRAP_SERVERS.split(":")
        sock = socket.create_connection((host, int(port)), timeout=3)
        sock.close()
        checks["redpanda"] = True
    except Exception:
        checks["redpanda"] = False

    # MinIO
    try:
        from minio import Minio

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
        client.list_buckets()
        checks["minio"] = True
    except Exception:
        checks["minio"] = False

    all_ok = all(checks.values())
    return {"ok": all_ok, "checks": checks}


@app.get("/api/_test/error")
async def test_error() -> None:
    """Endpoint that raises an unhandled exception for error-handler testing."""
    if settings.ENVIRONMENT != "development":
        raise HTTPException(status_code=404)
    raise RuntimeError("Intentional test error for error handler verification")


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    from app.lib.telemetry import metrics_endpoint

    return metrics_endpoint()


# ── API routes ───────────────────────────────────────────────────────────────

from fastapi import APIRouter

from app.api.routes.alerts import router as alerts_router
from app.api.routes.audit_routes import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.calibration import router as calibration_router
from app.api.routes.capabilities import router as capabilities_router
from app.api.routes.entities import router as entities_router
from app.api.routes.eval import router as eval_router
from app.api.routes.health import router as health_router
from app.api.routes.hypotheses import router as hypotheses_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.observations import router as observations_router
from app.api.routes.optimize import (
    incident_router as optimize_incident_router,
)
from app.api.routes.optimize import (
    router as optimize_router,
)
from app.api.routes.privacy import router as privacy_router
from app.api.routes.scenarios import router as scenarios_router
from app.api.routes.sensing import router as sensing_router
from app.api.routes.simulator import router as simulator_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.tasks import task_router as task_item_router
from app.api.routes.twin import router as twin_router
from app.api.routes.ws import router as ws_router
from app.realtime.manager import router as realtime_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(incidents_router)
api_router.include_router(observations_router)
api_router.include_router(hypotheses_router)
api_router.include_router(scenarios_router)
api_router.include_router(optimize_router)
api_router.include_router(optimize_incident_router)
api_router.include_router(twin_router)
api_router.include_router(privacy_router)
api_router.include_router(sensing_router)
api_router.include_router(simulator_router)
api_router.include_router(eval_router)
api_router.include_router(alerts_router)
api_router.include_router(tasks_router)
api_router.include_router(task_item_router)
api_router.include_router(entities_router)
api_router.include_router(audit_router)
api_router.include_router(ingest_router)
api_router.include_router(capabilities_router)
api_router.include_router(calibration_router)

app.include_router(api_router)
app.include_router(health_router)
app.include_router(ws_router)
app.include_router(realtime_router)
