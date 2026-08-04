"""FastAPI application entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.config import settings, validate_startup_configuration
from app.realtime.manager import manager as realtime_manager

logger = logging.getLogger("app.main")

validate_startup_configuration()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: seed users + start Kafka producer. Shutdown: stop producer."""
    validate_startup_configuration()
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
        await asyncio.wait_for(producer.start(), timeout=5.0)
        app.state.kafka_producer = producer
        logger.info("Kafka producer started")
    except Exception as exc:
        logger.warning("Kafka producer failed to start (non-fatal): %s", exc)
        app.state.kafka_producer = None

    async with anyio.create_task_group() as coordination_tasks:
        await realtime_manager.start(coordination_tasks)
        yield
        coordination_tasks.cancel_scope.cancel()

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
from app.middleware.cache_policy import ProtectedCachePolicyMiddleware
from app.middleware.error_handler import register_error_handlers
from app.middleware.org_context import OrgContextMiddleware
from app.middleware.request_id import RequestIDMiddleware

app.add_middleware(OrgContextMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(ProtectedCachePolicyMiddleware)

# Register global error handlers.
register_error_handlers(app)

# ── Telemetry (OpenTelemetry traces + Prometheus metrics) ───────────────────
from app.lib.telemetry import setup_telemetry

setup_telemetry(app)


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
from app.api.routes.edge_sync import router as edge_sync_router
from app.api.routes.entities import router as entities_router
from app.api.routes.eval import router as eval_router
from app.api.routes.health import router as health_router
from app.api.routes.hypotheses import router as hypotheses_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.observations import router as observations_router
from app.api.routes.observations_batch import (
    router as observations_batch_router,
)
from app.api.routes.optimize import (
    incident_router as optimize_incident_router,
)
from app.api.routes.optimize import (
    router as optimize_router,
)
from app.api.routes.privacy import router as privacy_router
from app.api.routes.privacy_controls import router as privacy_controls_router
from app.api.routes.scenarios import router as scenarios_router
from app.api.routes.sensing import router as sensing_router
from app.api.routes.service_health import router as service_health_router
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
api_router.include_router(observations_batch_router)
api_router.include_router(hypotheses_router)
api_router.include_router(scenarios_router)
api_router.include_router(optimize_router)
api_router.include_router(optimize_incident_router)
api_router.include_router(twin_router)
api_router.include_router(privacy_router)
api_router.include_router(privacy_controls_router)
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
api_router.include_router(edge_sync_router)

app.include_router(api_router)
app.include_router(service_health_router)
app.include_router(health_router)
app.include_router(ws_router)
app.include_router(realtime_router)
