"""Capabilities endpoint — runtime feature availability for blocker handling protocol.

GET /api/capabilities returns a list of features with status:
  - available:   feature is configured and reachable
  - degraded:    feature is configured but partially functional
  - unavailable: feature is not configured or unreachable

Each feature includes ``activation_steps`` describing how to enable it.
All checks are best-effort: a check failure never crashes the endpoint.
The system continues with unblocked work when a blocker is hit.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.lib.time import now_ms

logger = logging.getLogger("app.api.routes.capabilities")

router = APIRouter(tags=["capabilities"])

# Local data directory — same path calculation as sensing.py.
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
_MODELS_DIR = os.path.join(_DATA_DIR, "models")
_MANIFEST_PATH = os.path.join(_MODELS_DIR, "manifests.json")

# Activation step templates.
_ONNX_STEPS = (
    "Install onnxruntime (pip install onnxruntime) and download model "
    "weights via scripts/download_models.py --download"
)
_LLM_STEPS = (
    "Set OLLAMA_BASE_URL env var, start Ollama, and run "
    "'ollama pull llama3.1:8b'"
)
_PMTILES_STEPS = (
    "Set PMTILES_PATH env var to a .pmtiles file path, or run "
    "scripts/offline_prep.sh to generate one via tippecanoe"
)
_WEIGHTS_STEPS = (
    "Run scripts/download_models.py --download to fetch model weights "
    "from HuggingFace and upload to MinIO"
)
_KAFKA_STEPS = (
    "Set KAFKA_BOOTSTRAP_SERVERS env var to the broker address, or "
    "start Redpanda via 'docker compose up redpanda'"
)
_REDIS_STEPS = (
    "Set REDIS_URL env var to the Redis connection URL, or start Redis "
    "via 'docker compose up redis'"
)


def _manifests_validation_state() -> str | None:
    """Inspect model manifests and report validation state.

    Reads ``data/models/manifests.json`` at request time and returns:
      - ``"validated"``  if every model has ``validation_status == "validated"``
        AND ``signed`` is true.
      - ``"placeholder"`` if ANY model has ``validation_status != "validated"``
        OR ``signed`` is not true.
      - ``None`` if the manifest file is missing, empty, or malformed —
        callers should fall back to file-existence checks in that case.
    """
    if not os.path.isfile(_MANIFEST_PATH):
        return None
    try:
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as fh:
            manifests = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("manifest load failed (%s): %s", _MANIFEST_PATH, exc)
        return None
    if not isinstance(manifests, list) or not manifests:
        return None
    for entry in manifests:
        if not isinstance(entry, dict):
            return None
        if entry.get("validation_status") != "validated" or entry.get("signed") is not True:
            return "placeholder"
    return "validated"


def _check_onnx_models() -> dict[str, str]:
    """Check if ONNX runtime is importable and model files exist."""
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return {
            "feature": "onnx_models",
            "status": "unavailable",
            "activation_steps": _ONNX_STEPS,
        }

    has_weights = (
        os.path.isdir(_MODELS_DIR)
        and any(f.endswith(".onnx") for f in os.listdir(_MODELS_DIR))
    )
    if has_weights:
        manifest_state = _manifests_validation_state()
        if manifest_state == "placeholder":
            return {
                "feature": "onnx_models",
                "status": "degraded",
                "activation_steps": _ONNX_STEPS,
            }
        return {
            "feature": "onnx_models",
            "status": "available",
            "activation_steps": _ONNX_STEPS,
        }
    return {
        "feature": "onnx_models",
        "status": "degraded",
        "activation_steps": _ONNX_STEPS,
    }


def _check_ollama_llm() -> dict[str, str]:
    """Check if Ollama LLM is reachable via HTTP."""
    base_url = os.environ.get("OLLAMA_BASE_URL") or settings.OLLAMA_BASE_URL
    if not base_url:
        return {
            "feature": "ollama_llm",
            "status": "unavailable",
            "activation_steps": _LLM_STEPS,
        }
    try:
        import urllib.request

        with urllib.request.urlopen(
            f"{base_url}/api/tags", timeout=2
        ) as resp:
            if resp.status == 200:
                return {
                    "feature": "ollama_llm",
                    "status": "available",
                    "activation_steps": _LLM_STEPS,
                }
    except Exception:
        pass
    return {
        "feature": "ollama_llm",
        "status": "unavailable",
        "activation_steps": _LLM_STEPS,
    }


def _check_pmtiles_basemap() -> dict[str, str]:
    """Check if PMTiles basemap file exists."""
    pmtiles_path = os.environ.get("PMTILES_PATH")
    if pmtiles_path and os.path.exists(pmtiles_path):
        return {
            "feature": "pmtiles_basemap",
            "status": "available",
            "activation_steps": _PMTILES_STEPS,
        }
    return {
        "feature": "pmtiles_basemap",
        "status": "unavailable",
        "activation_steps": _PMTILES_STEPS,
    }


def _check_model_weights() -> dict[str, str]:
    """Check if model weight files exist in the local data directory."""
    if os.path.isdir(_MODELS_DIR):
        onnx_files = [f for f in os.listdir(_MODELS_DIR) if f.endswith(".onnx")]
        if onnx_files:
            manifest_state = _manifests_validation_state()
            if manifest_state == "placeholder":
                return {
                    "feature": "model_weights",
                    "status": "degraded",
                    "activation_steps": _WEIGHTS_STEPS,
                }
            return {
                "feature": "model_weights",
                "status": "available",
                "activation_steps": _WEIGHTS_STEPS,
            }
    return {
        "feature": "model_weights",
        "status": "unavailable",
        "activation_steps": _WEIGHTS_STEPS,
    }


def _check_kafka() -> dict[str, str]:
    """Check if Kafka/Redpanda is configured and TCP-reachable."""
    bootstrap = (
        os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
        or settings.REDPANDA_BOOTSTRAP_SERVERS
    )
    if not bootstrap:
        return {
            "feature": "kafka",
            "status": "unavailable",
            "activation_steps": _KAFKA_STEPS,
        }
    try:
        host, port = bootstrap.split(":")
        sock = socket.create_connection((host, int(port)), timeout=2)
        sock.close()
        return {
            "feature": "kafka",
            "status": "available",
            "activation_steps": _KAFKA_STEPS,
        }
    except Exception:
        return {
            "feature": "kafka",
            "status": "degraded",
            "activation_steps": _KAFKA_STEPS,
        }


def _check_redis() -> dict[str, str]:
    """Check if Redis is configured and pingable."""
    redis_url = os.environ.get("REDIS_URL") or settings.REDIS_URL
    if not redis_url:
        return {
            "feature": "redis",
            "status": "unavailable",
            "activation_steps": _REDIS_STEPS,
        }
    try:
        import redis

        client = redis.from_url(redis_url, socket_connect_timeout=2)
        client.ping()
        return {
            "feature": "redis",
            "status": "available",
            "activation_steps": _REDIS_STEPS,
        }
    except Exception:
        return {
            "feature": "redis",
            "status": "degraded",
            "activation_steps": _REDIS_STEPS,
        }


_CHECKS = (
    _check_onnx_models,
    _check_ollama_llm,
    _check_pmtiles_basemap,
    _check_model_weights,
    _check_kafka,
    _check_redis,
)


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """Return runtime availability of all platform features.

    Each feature is checked at request time — statuses are not hardcoded.
    A check failure never crashes the endpoint; the feature is reported
    as ``unavailable`` instead.
    """
    features = []
    for check in _CHECKS:
        try:
            features.append(check())
        except Exception as exc:
            logger.warning("capability check %s failed: %s", check.__name__, exc)
            features.append({
                "feature": check.__name__.replace("_check_", ""),
                "status": "unavailable",
                "activation_steps": "See documentation for activation steps.",
            })
    return {
        "features": features,
        "checked_at_ms": now_ms(),
    }


__all__ = ["router"]
