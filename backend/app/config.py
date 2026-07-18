"""Application configuration via Pydantic Settings (env vars)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+psycopg://disaster:disaster@db:5432/disaster"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Redpanda (Kafka)
    REDPANDA_BOOTSTRAP_SERVERS: str = "redpanda:9092"

    # MinIO (S3-compatible object storage)
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"

    # Ollama (local LLM)
    OLLAMA_BASE_URL: str = "http://ollama:11434"

    # Auth / JWT
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # CORS (comma-separated origins, or * for all)
    CORS_ORIGINS: str = "*"

    # Environment
    ENVIRONMENT: str = "development"


settings = Settings()
