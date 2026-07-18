"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: seed users + start Kafka producer. Shutdown: stop producer."""
    # 1. Create users table (not in Alembic migration) + seed demo users.
    from app.auth.seed import seed_demo_users
    from app.db import SessionLocal, Base, engine
    from app.models.user import User

    Base.metadata.create_all(bind=engine, tables=[User.__table__])
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
origins = (
    ["*"] if settings.CORS_ORIGINS == "*" else settings.CORS_ORIGINS.split(",")
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware order (last added = outermost = runs first on request):
# RequestID → OrgContext → CORS → router
from app.middleware.error_handler import register_error_handlers  # noqa: E402
from app.middleware.org_context import OrgContextMiddleware  # noqa: E402
from app.middleware.request_id import RequestIDMiddleware  # noqa: E402

app.add_middleware(OrgContextMiddleware)
app.add_middleware(RequestIDMiddleware)

# Register global error handlers.
register_error_handlers(app)

# ── Telemetry (OpenTelemetry traces + Prometheus metrics) ───────────────────
from app.lib.telemetry import setup_telemetry  # noqa: E402

setup_telemetry(app)


# ── Health checks ───────────────────────────────────────────────────────────


@app.get("/healthz")
async def healthz() -> dict:
    """Shallow health check — returns service bindings without testing connectivity."""
    return {
        "ok": True,
        "bindings": {
            "database": settings.DATABASE_URL,
            "redis": settings.REDIS_URL,
            "redpanda": settings.REDPANDA_BOOTSTRAP_SERVERS,
            "minio": settings.MINIO_ENDPOINT,
            "ollama": settings.OLLAMA_BASE_URL,
        },
        "environment": settings.ENVIRONMENT,
    }


@app.get("/healthz/deep")
async def healthz_deep() -> dict:
    """Deep health check — tests connectivity to PostgreSQL, Redis, and MinIO."""
    checks: dict[str, dict] = {}

    # PostgreSQL
    try:
        from app.db import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)}

    # Redis
    try:
        import redis

        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        checks["redis"] = {"ok": True}
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": str(exc)}

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
        checks["minio"] = {"ok": True}
    except Exception as exc:
        checks["minio"] = {"ok": False, "error": str(exc)}

    all_ok = all(c.get("ok", False) for c in checks.values())
    return {"ok": all_ok, "checks": checks}


@app.get("/api/_test/error")
async def test_error() -> None:
    """Endpoint that raises an unhandled exception for error-handler testing."""
    raise RuntimeError("Intentional test error for error handler verification")


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from app.lib.telemetry import metrics_endpoint

    return metrics_endpoint()


# ── API routes ───────────────────────────────────────────────────────────────

from app.api.routes.auth import router as auth_router  # noqa: E402
from app.api.routes.eval import router as eval_router  # noqa: E402
from app.api.routes.hypotheses import router as hypotheses_router  # noqa: E402
from app.api.routes.observations import router as observations_router  # noqa: E402
from app.api.routes.optimize import router as optimize_router  # noqa: E402
from app.api.routes.scenarios import router as scenarios_router  # noqa: E402
from app.api.routes.sensing import router as sensing_router  # noqa: E402
from app.api.routes.ws import router as ws_router  # noqa: E402
from fastapi import APIRouter  # noqa: E402

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(observations_router)
api_router.include_router(hypotheses_router)
api_router.include_router(scenarios_router)
api_router.include_router(optimize_router)
api_router.include_router(sensing_router)
api_router.include_router(eval_router)

app.include_router(api_router)
app.include_router(ws_router)
