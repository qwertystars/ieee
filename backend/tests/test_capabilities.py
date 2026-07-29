"""Tests for the capabilities endpoint — blocker handling protocol (T39).

Verifies that GET /api/capabilities:
1. Returns 200
2. Lists all 6 expected features
3. Each feature has feature name, status, and activation_steps
4. Status values are valid (available|degraded|unavailable)
5. activation_steps is a non-empty string
6. Endpoint does not crash when dependencies are down

Tests run against the real environment. Service reachability is detected at
test time so the assertions hold whether dependencies are up or down.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

EXPECTED_FEATURES = {
    "onnx_models",
    "ollama_llm",
    "pmtiles_basemap",
    "model_weights",
    "kafka",
    "redis",
}

VALID_STATUSES = {"available", "degraded", "unavailable"}


def _check_service_reachable(host: str, port: int) -> bool:
    """TCP-connect to (host, port) with a 2s timeout. True if reachable."""
    try:
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        return True
    except OSError:
        return False


def _parse_host_port(addr: str, default_port: int) -> tuple[str, int]:
    """Extract (host, port) from a URL or bare ``host:port`` string."""
    parsed = urlparse(addr)
    if parsed.hostname:
        return parsed.hostname, parsed.port or default_port
    host, _, port = addr.partition(":")
    return host, int(port) if port else default_port


def test_capabilities_returns_200() -> None:
    """GET /api/capabilities returns HTTP 200."""
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    assert resp.status_code == 200


def test_capabilities_returns_all_features() -> None:
    """Response includes all 6 expected features."""
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    body = resp.json()
    features = body["features"]
    feature_names = {f["feature"] for f in features}
    assert feature_names == EXPECTED_FEATURES, (
        f"missing features: {EXPECTED_FEATURES - feature_names}, "
        f"extra features: {feature_names - EXPECTED_FEATURES}"
    )


def test_capabilities_each_feature_has_status() -> None:
    """Each feature has a status field with a valid value."""
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    features = resp.json()["features"]
    for feat in features:
        assert "status" in feat, f"feature {feat['feature']} missing status"
        assert feat["status"] in VALID_STATUSES, (
            f"feature {feat['feature']} has invalid status: {feat['status']}"
        )


def test_capabilities_each_feature_has_activation_steps() -> None:
    """Each feature has non-empty activation_steps."""
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    features = resp.json()["features"]
    for feat in features:
        assert "activation_steps" in feat, (
            f"feature {feat['feature']} missing activation_steps"
        )
        assert isinstance(feat["activation_steps"], str), (
            f"feature {feat['feature']} activation_steps is not a string"
        )
        assert len(feat["activation_steps"]) > 0, (
            f"feature {feat['feature']} has empty activation_steps"
        )


def test_capabilities_includes_timestamp() -> None:
    """Response includes a checked_at_ms timestamp."""
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    body = resp.json()
    assert "checked_at_ms" in body
    assert isinstance(body["checked_at_ms"], int)
    assert body["checked_at_ms"] > 0


def test_capabilities_does_not_crash_when_deps_down() -> None:
    """Endpoint returns 200 regardless of whether Redis, Kafka, or Ollama are up.

    Detects actual service reachability at test time via a TCP socket check
    and asserts the capabilities endpoint reports the matching status —
    ``available`` when reachable, ``unavailable``/``degraded`` otherwise.
    """
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    features = {f["feature"]: f["status"] for f in resp.json()["features"]}

    redis_url = os.environ.get("REDIS_URL") or settings.REDIS_URL
    redis_host, redis_port = _parse_host_port(redis_url, default_port=6379)
    if _check_service_reachable(redis_host, redis_port):
        assert features["redis"] == "available", (
            f"redis reachable at {redis_host}:{redis_port} but status="
            f"{features['redis']!r}"
        )
    else:
        assert features["redis"] in ("unavailable", "degraded"), (
            f"redis unreachable at {redis_host}:{redis_port} but status="
            f"{features['redis']!r}"
        )

    kafka_bootstrap = (
        os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
        or settings.REDPANDA_BOOTSTRAP_SERVERS
    )
    kafka_host, kafka_port = _parse_host_port(kafka_bootstrap, default_port=9092)
    if _check_service_reachable(kafka_host, kafka_port):
        assert features["kafka"] == "available", (
            f"kafka reachable at {kafka_host}:{kafka_port} but status="
            f"{features['kafka']!r}"
        )
    else:
        assert features["kafka"] in ("unavailable", "degraded"), (
            f"kafka unreachable at {kafka_host}:{kafka_port} but status="
            f"{features['kafka']!r}"
        )

    ollama_url = os.environ.get("OLLAMA_BASE_URL") or settings.OLLAMA_BASE_URL
    ollama_host, ollama_port = _parse_host_port(ollama_url, default_port=11434)
    if _check_service_reachable(ollama_host, ollama_port):
        assert features["ollama_llm"] == "available", (
            f"ollama reachable at {ollama_host}:{ollama_port} but status="
            f"{features['ollama_llm']!r}"
        )
    else:
        assert features["ollama_llm"] in ("unavailable", "degraded"), (
            f"ollama unreachable at {ollama_host}:{ollama_port} but status="
            f"{features['ollama_llm']!r}"
        )


def test_capabilities_feature_count() -> None:
    """Response contains exactly 6 features (no more, no less)."""
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    features = resp.json()["features"]
    assert len(features) == 6, f"expected 6 features, got {len(features)}"
