"""Tests for the capabilities endpoint — blocker handling protocol (T39).

Verifies that GET /api/capabilities:
1. Returns 200
2. Lists all 6 expected features
3. Each feature has feature name, status, and activation_steps
4. Status values are valid (available|degraded|unavailable)
5. activation_steps is a non-empty string
6. Endpoint does not crash when dependencies are down

Tests run against the real environment (Redis down, Kafka down, Ollama down)
to verify the endpoint handles unavailable dependencies gracefully.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

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
    """Endpoint returns 200 even when Redis, Kafka, and Ollama are down.

    In the test environment, these dependencies are unavailable. The
    endpoint must report them as unavailable/degraded, not crash.
    """
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    features = {f["feature"]: f["status"] for f in resp.json()["features"]}

    # Redis and Kafka are down in the test environment — must be
    # unavailable or degraded, never cause a 500.
    assert features["redis"] in ("unavailable", "degraded")
    assert features["kafka"] in ("unavailable", "degraded")
    assert features["ollama_llm"] in ("unavailable", "degraded")


def test_capabilities_feature_count() -> None:
    """Response contains exactly 6 features (no more, no less)."""
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    features = resp.json()["features"]
    assert len(features) == 6, f"expected 6 features, got {len(features)}"
