"""Application configuration and production safety gates."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Final, Literal, Self
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEVELOPMENT_SECRET_MARKERS: Final = frozenset(
    {
        "dev-secret-change-me",
        "dev-secret-change-me-for-local-dev-only-32chars",
        "change-me",
        "password",
        "secret",
        "minio123",
        "admin",
        "disaster",
        "resqnet123",
    }
)
_DEVELOPMENT_CREDENTIALS: Final = frozenset(
    {
        ("disaster", "disaster"),
        ("resqnet", "resqnet123"),
    }
)


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Database
    DATABASE_URL: str = "postgresql+psycopg://disaster:disaster@db:5432/disaster"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_REVOCATION_REQUIRED: bool = True
    REVOCATION_PROPAGATION_DEADLINE_SECONDS: int = 60
    REALTIME_FANOUT_CHANNEL: str = "resqnet:realtime"
    EVALUATION_JOB_TTL_DAYS: int = 7
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Redpanda (Kafka)
    REDPANDA_BOOTSTRAP_SERVERS: str = "redpanda:9092"

    # Worker concurrency (number of parallel consumer instances)
    WORKER_CONCURRENCY: int = 1

    # MinIO (S3-compatible object storage)
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minio"
    MINIO_SECRET_KEY: str = "minio123"

    # Ollama (local LLM)
    OLLAMA_BASE_URL: str = "http://ollama:11434"

    # Auth / JWT
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "resqnet-sage"
    HUMAN_ACCESS_AUDIENCE: str = "resqnet-api"
    DEVICE_ACCESS_AUDIENCE: str = "resqnet-device"
    SERVICE_ACCESS_AUDIENCE: str = "resqnet-service"
    REFRESH_TOKEN_AUDIENCE: str = "resqnet-refresh"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES: int = 5
    SERVICE_ACCESS_TOKEN_EXPIRE_MINUTES: int = 5
    REFRESH_TOKEN_ROTATION_REQUIRED: bool = True
    REFRESH_TOKEN_ROTATION_GRACE_SECONDS: int = 0

    # CORS (comma-separated origins, or * for all)
    CORS_ORIGINS: str = "*"

    # Deployment controls. These are explicit so CI and startup share a contract.
    UVICORN_RELOAD: bool = False
    SOURCE_MOUNTS_ENABLED: bool = False
    MOCK_BINDINGS_ENABLED: bool = False
    EXPOSE_INTERNAL_PORTS: bool = False

    # Environment
    ENVIRONMENT: str = "development"
    SIMULATOR_TRANSPORT: Literal["kafka", "database"] = "kafka"

    def production_violations(self) -> tuple[str, ...]:
        """Return names of unsafe controls without exposing configured values."""
        if self.ENVIRONMENT.lower() != "production":
            return ()

        violations: list[str] = []
        if self.SIMULATOR_TRANSPORT != "kafka":
            violations.append("SIMULATOR_TRANSPORT")
        secret = self.JWT_SECRET.lower()
        development_secret = secret in _DEVELOPMENT_SECRET_MARKERS or any(
            marker in secret
            for marker in ("dev-secret", "local-development", "change-for-real-use")
        )
        if len(self.JWT_SECRET) < 32 or development_secret:
            violations.append("JWT_SECRET")
        if self.JWT_ALGORITHM not in {"HS256", "HS384", "HS512"}:
            violations.append("JWT_ALGORITHM")
        audiences = (
            self.HUMAN_ACCESS_AUDIENCE,
            self.DEVICE_ACCESS_AUDIENCE,
            self.SERVICE_ACCESS_AUDIENCE,
            self.REFRESH_TOKEN_AUDIENCE,
        )
        if not self.JWT_ISSUER or any(not audience for audience in audiences):
            violations.append("JWT_IDENTITY_METADATA")
        if not self.REDIS_REVOCATION_REQUIRED:
            violations.append("REDIS_REVOCATION_REQUIRED")
        if not self.REFRESH_TOKEN_ROTATION_REQUIRED:
            violations.append("REFRESH_TOKEN_ROTATION_REQUIRED")
        if not 1 <= self.ACCESS_TOKEN_EXPIRE_MINUTES <= 15:
            violations.append("ACCESS_TOKEN_EXPIRE_MINUTES")
        if not 1 <= self.REFRESH_TOKEN_EXPIRE_DAYS <= 7:
            violations.append("REFRESH_TOKEN_EXPIRE_DAYS")
        if not 1 <= self.DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES <= 5:
            violations.append("DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES")
        if not 1 <= self.SERVICE_ACCESS_TOKEN_EXPIRE_MINUTES <= 5:
            violations.append("SERVICE_ACCESS_TOKEN_EXPIRE_MINUTES")
        if self.REFRESH_TOKEN_ROTATION_GRACE_SECONDS != 0:
            violations.append("REFRESH_TOKEN_ROTATION_GRACE_SECONDS")
        if self.REVOCATION_PROPAGATION_DEADLINE_SECONDS > 60:
            violations.append("REVOCATION_PROPAGATION_DEADLINE_SECONDS")

        origins = tuple(origin.strip() for origin in self.CORS_ORIGINS.split(","))
        if not origins or any(not origin for origin in origins) or "*" in origins:
            violations.append("CORS_ORIGINS")
        if self.UVICORN_RELOAD:
            violations.append("UVICORN_RELOAD")
        if self.SOURCE_MOUNTS_ENABLED:
            violations.append("SOURCE_MOUNTS_ENABLED")
        if self.MOCK_BINDINGS_ENABLED:
            violations.append("MOCK_BINDINGS_ENABLED")
        if self.EXPOSE_INTERNAL_PORTS:
            violations.append("EXPOSE_INTERNAL_PORTS")

        parsed_database = urlparse(self.DATABASE_URL)
        database_credentials = (parsed_database.username, parsed_database.password)
        if database_credentials in _DEVELOPMENT_CREDENTIALS or any(
            isinstance(value, str) and "local-dev" in value.lower()
            for value in database_credentials
        ):
            violations.append("DATABASE_URL")
        if (
            self.MINIO_ACCESS_KEY.lower() in {"minio", "admin"}
            or "local-dev" in self.MINIO_ACCESS_KEY.lower()
        ):
            violations.append("MINIO_ACCESS_KEY")
        if (
            self.MINIO_SECRET_KEY.lower() in _DEVELOPMENT_SECRET_MARKERS
            or "local-dev" in self.MINIO_SECRET_KEY.lower()
        ):
            violations.append("MINIO_SECRET_KEY")
        return tuple(dict.fromkeys(violations))

    @model_validator(mode="after")
    def _validate_security_contract(self) -> Self:
        """Reject unsafe production settings before the application is served."""
        violations = self.production_violations()
        if violations:
            raise ValueError(
                "unsafe production configuration: " + ", ".join(violations)
            )
        return self


settings = Settings()


def validate_startup_configuration(argv: Sequence[str] | None = None) -> None:
    """Reject production reload flags before FastAPI starts serving requests."""
    arguments = tuple(sys.argv if argv is None else argv)
    violations = list(settings.production_violations())
    if settings.ENVIRONMENT.lower() == "production" and "--reload" in arguments:
        violations.append("reload")
    if violations:
        raise RuntimeError(
            "unsafe production configuration: " + ", ".join(dict.fromkeys(violations))
        )


__all__ = ["Settings", "settings", "validate_startup_configuration"]
