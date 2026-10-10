"""Artifact retrieval, registry metadata, and in-memory session cache."""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.perception.models import ModelRecord
from app.perception.serving_contracts import (
    ContractResolution,
    ContractState,
    InferenceContract,
    InferenceContractError,
)

if TYPE_CHECKING:
    import onnxruntime as ort


class MinioLike:
    def get_object(self, bucket: str, key: str) -> Any:
        raise NotImplementedError


@dataclass(slots=True)
class CachedModel:
    session: ort.InferenceSession
    contract: InferenceContract | None
    model_name: str
    version: str
    last_used_ms: int


class ModelStorageMixin:
    """Storage operations mixed into the serving lifecycle class."""

    _lock: threading.Lock
    _cache: dict[str, CachedModel]
    _session_factory: Callable[[], Session]
    _cache_dir: str | None
    _minio: MinioLike | None

    def _cached(self, model_id: str) -> CachedModel | None:
        with self._lock:
            cached = self._cache.get(model_id)
            if cached is not None:
                cached.last_used_ms = now_ms()
            return cached

    def _revalidate_cached(
        self,
        model_id: str,
        cached: CachedModel,
        contract: InferenceContract,
    ) -> None:
        try:
            self._get_model_bytes(contract.artifact_key, contract.artifact_sha256)
        except (FileNotFoundError, RuntimeError) as exc:
            with self._lock:
                self._cache.pop(model_id, None)
            raise InferenceContractError(ContractResolution(
                ContractState.unavailable, contract, "weights_unavailable",
            )) from exc

    def _get_model_metadata(self, model_id: str) -> ModelRecord:
        db = self._session_factory()
        try:
            record = db.get(ModelRecord, model_id)
            if record is None:
                raise KeyError(f"model {model_id} not found in registry")
            return record
        finally:
            db.close()

    def _cache_session(
        self,
        model_id: str,
        session: ort.InferenceSession,
        contract: InferenceContract | None,
        model_name: str,
        version: str,
    ) -> None:
        with self._lock:
            self._cache[model_id] = CachedModel(
                session=session,
                contract=contract,
                model_name=model_name,
                version=version,
                last_used_ms=now_ms(),
            )

    def _get_model_bytes(self, r2_key: str, expected_sha256: str | None = None) -> bytes:
        if self._cache_dir is not None:
            local_path = os.path.join(self._cache_dir, r2_key.replace("/", os.sep))
            if os.path.isfile(local_path):
                with open(local_path, "rb") as model_file:
                    data = model_file.read()
                if expected_sha256 is not None and hashlib.sha256(data).hexdigest() != expected_sha256:
                    raise RuntimeError("artifact checksum mismatch")
                return data
        if self._minio is None:
            raise RuntimeError("weights unavailable")
        bucket, _, key = r2_key.partition("/")
        response = self._minio.get_object(bucket, key)
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()
        if expected_sha256 is not None and hashlib.sha256(data).hexdigest() != expected_sha256:
            raise RuntimeError("artifact checksum mismatch")
        return data

    @staticmethod
    def _create_session(model_bytes: bytes) -> ort.InferenceSession:
        import onnxruntime as ort
        return ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])


__all__ = ["CachedModel", "MinioLike", "ModelStorageMixin"]
