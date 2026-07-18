"""Model serving layer — ONNX Runtime inference with lazy loading.

Designed for local hardware with limited resources: models are loaded on
first request, cached in memory, and unloaded after an idle timeout.

The ``ModelServing`` class is the single entry point for ML inference.
T18 (SAR flood mapping), T19 (ensemble), T20 (damage), and T21 (NLP)
all use this layer — they never touch ONNX Runtime directly.

Model weights live in MinIO (S3-compatible) at ``r2_key``. On first load,
weights are downloaded and an ``onnxruntime.InferenceSession`` is created
with the CPU execution provider. The session is cached in a thread-safe
in-memory dict keyed by ``model_id``.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.perception.models import ModelRecord

logger = logging.getLogger(__name__)

# Default idle timeout: 5 minutes. Models not accessed within this window
# are eligible for unloading to free memory.
DEFAULT_IDLE_TIMEOUT_S = 300


@dataclass(slots=True)
class _CachedModel:
    """An in-memory cached ONNX inference session with usage tracking."""

    session: Any
    model_name: str
    version: str
    last_used_ms: int


# ─── Model catalog ─────────────────────────────────────────────────────────
# Static catalog of models to pre-cache for offline operation. The download
# script (scripts/download_models.py) reads this to know what to fetch.
# ``source_url`` is the upstream URL; ``r2_key`` is the MinIO object key.

MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "name": "sar-flood-mapping",
        "version": "1.0.0",
        "framework": "onnx",
        "task": "flood_mapping",
        "r2_key": "models/sar-flood-mapping-v1.0.0.onnx",
        "source_url": "https://huggingface.co/resqnet/sar-flood-mapping/resolve/v1.0.0/model.onnx",
        "input_schema": {"bands": ["VV", "VH"], "shape": [1, 2, 512, 512]},
        "output_schema": {"flood_mask": [1, 1, 512, 512]},
        "calibration_metrics": {"iou": 0.87, "precision": 0.91},
    },
    {
        "name": "building-damage",
        "version": "1.0.0",
        "framework": "onnx",
        "task": "damage",
        "r2_key": "models/building-damage-v1.0.0.onnx",
        "source_url": "https://huggingface.co/resqnet/building-damage/resolve/v1.0.0/model.onnx",
        "input_schema": {"bands": ["B2", "B3", "B4", "B8"], "shape": [1, 4, 256, 256]},
        "output_schema": {"damage_class": [1, 4, 256, 256]},
        "calibration_metrics": {"f1": 0.83, "recall": 0.79},
    },
    {
        "name": "incident-nlp",
        "version": "1.0.0",
        "framework": "onnx",
        "task": "nlp",
        "r2_key": "models/incident-nlp-v1.0.0.onnx",
        "source_url": "https://huggingface.co/resqnet/incident-nlp/resolve/v1.0.0/model.onnx",
        "input_schema": {"input_ids": [1, 128], "attention_mask": [1, 128]},
        "output_schema": {"logits": [1, 7]},
        "calibration_metrics": {"accuracy": 0.89},
    },
]


def format_catalog() -> str:
    """Format the model catalog as a human-readable table for ``--list``."""
    lines = [
        f"{'Name':<25} {'Version':<10} {'Framework':<10} {'Task':<15} {'R2 Key'}",
        "-" * 90,
    ]
    for m in MODEL_CATALOG:
        lines.append(
            f"{m['name']:<25} {m['version']:<10} {m['framework']:<10} "
            f"{m['task']:<15} {m['r2_key']}"
        )
    return "\n".join(lines)


# ─── ModelServing ──────────────────────────────────────────────────────────


class ModelServing:
    """ONNX Runtime inference with lazy loading and idle eviction.

    Thread-safe. The in-memory cache maps ``model_id`` to a ``_CachedModel``
    holding the ``InferenceSession``, model version, and last-used timestamp.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        minio_client: Any | None = None,
        cache_dir: str | None = None,
    ):
        self._session_factory = session_factory
        self._minio = minio_client
        self._cache_dir = cache_dir
        self._cache: dict[str, _CachedModel] = {}
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────────────

    def load_model(self, model_id: str) -> Any:
        """Lazy-load a model, returning the cached ``InferenceSession``.

        First call downloads weights from MinIO and creates the session.
        Subsequent calls return the cached session and update ``last_used_ms``.
        """
        with self._lock:
            cached = self._cache.get(model_id)
            if cached is not None:
                cached.last_used_ms = now_ms()
                return cached.session

        meta = self._get_model_metadata(model_id)
        model_bytes = self._get_model_bytes(meta.r2_key)
        session = self._create_session(model_bytes)
        with self._lock:
            self._cache[model_id] = _CachedModel(
                session=session,
                model_name=meta.name,
                version=meta.version,
                last_used_ms=now_ms(),
            )
        logger.info("loaded model %s:%s", meta.name, meta.version)
        return session

    def run_inference(self, model_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Run inference and return outputs with ``model_version`` for provenance.

        The ``model_version`` field (``name:version``) is what gets recorded
        on the observation's ``model_version`` column.
        """
        session = self.load_model(model_id)
        with self._lock:
            cached = self._cache[model_id]
            model_version = f"{cached.model_name}:{cached.version}"
        outputs = self._run_session(session, input_data)
        return {"outputs": outputs, "model_version": model_version}

    def unload_model(self, model_id: str) -> bool:
        """Manually unload a model from the cache. Returns True if it was cached."""
        with self._lock:
            cached = self._cache.pop(model_id, None)
        if cached is None:
            return False
        logger.info("unloaded model %s:%s", cached.model_name, cached.version)
        return True

    def unload_idle_models(self, timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_S) -> list[str]:
        """Unload models idle for longer than ``timeout_seconds``.

        Returns the list of unloaded model IDs.
        """
        cutoff = now_ms() - timeout_seconds * 1000
        unloaded: list[str] = []
        with self._lock:
            for mid in list(self._cache.keys()):
                if self._cache[mid].last_used_ms < cutoff:
                    cached = self._cache.pop(mid)
                    unloaded.append(mid)
                    logger.info("idle-unloaded model %s:%s", cached.model_name, cached.version)
        return unloaded

    # ── Internals ────────────────────────────────────────────────────────

    def _get_model_metadata(self, model_id: str) -> ModelRecord:
        """Fetch model metadata from the ``models`` registry table."""
        db = self._session_factory()
        try:
            record = db.get(ModelRecord, model_id)
            if record is None:
                raise KeyError(f"model {model_id} not found in registry")
            return record
        finally:
            db.close()

    def _get_model_bytes(self, r2_key: str) -> bytes:
        """Get model weights from local cache or MinIO."""
        if self._cache_dir is not None:
            local_path = os.path.join(self._cache_dir, r2_key.replace("/", os.sep))
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    return f.read()
        return self._download_from_minio(r2_key)

    def _download_from_minio(self, r2_key: str) -> bytes:
        """Download model weights from MinIO (S3-compatible)."""
        if self._minio is None:
            raise RuntimeError("no MinIO client configured")
        bucket, _, key = r2_key.partition("/")
        response = self._minio.get_object(bucket, key)
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()
        return data

    def _create_session(self, model_bytes: bytes) -> Any:
        """Create an ONNX Runtime inference session with CPU provider."""
        import onnxruntime as ort

        return ort.InferenceSession(
            model_bytes,
            providers=["CPUExecutionProvider"],
        )

    def _run_session(self, session: Any, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute inference and map outputs by name."""
        input_names = [i.name for i in session.get_inputs()]
        feeds = {name: input_data[name] for name in input_names if name in input_data}
        results = session.run(None, feeds)
        output_names = [o.name for o in session.get_outputs()]
        return dict(zip(output_names, results))


__all__ = [
    "DEFAULT_IDLE_TIMEOUT_S",
    "MODEL_CATALOG",
    "ModelServing",
    "format_catalog",
]
