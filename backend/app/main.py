"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings

app = FastAPI(
    title="ResQNet-SAGE",
    description="Disaster Situational Awareness & Response Platform",
    version="0.1.0",
)

# CORS
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
