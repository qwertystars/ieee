"""Manifest-bound model cache and ONNX serving lifecycle."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from sqlalchemy.orm import Session

from app.lib.observability import telemetry_span
from app.lib.observability_metrics import record_model_inference
from app.lib.time import now_ms
from app.perception.serving_contracts import (
    ContractResolution,
    ContractState,
    ContractVersions,
    InferenceContract,
    InferenceContractError,
    resolve_contract,
)
from app.perception.serving_execution import (
    build_provenance,
    run_session,
    validate_inputs,
)
from app.perception.serving_storage import CachedModel, ModelStorageMixin

if TYPE_CHECKING:
    import onnxruntime as ort

DEFAULT_IDLE_TIMEOUT_S = 300
_DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "manifests.json"


class ModelServing(ModelStorageMixin):
    """Lazy ONNX serving with strict manifest and tensor validation."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        minio_client: Any | None = None,
        cache_dir: str | None = None,
        manifest_path: Path | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._minio = minio_client
        self._cache_dir = cache_dir
        self._manifest_path = manifest_path or _DEFAULT_MANIFEST_PATH
        self._cache: dict[str, CachedModel] = {}
        self._lock = threading.Lock()

    def _resolve(
        self,
        model_id: str,
        requested: ContractVersions | None = None,
    ) -> ContractResolution:
        return resolve_contract(model_id, self._manifest_path, requested)

    def load_model(self, model_id: str) -> ort.InferenceSession:
        """Load a DB-registered model only when its manifest contract exists."""
        record = self._get_model_metadata(model_id)
        resolution = self._resolve(record.name)
        if resolution.contract is None or resolution.state is not ContractState.available:
            raise InferenceContractError(resolution)
        contract = resolution.contract
        if record.version != contract.versions.model_version or record.r2_key != contract.artifact_key:
            raise InferenceContractError(ContractResolution(
                ContractState.incompatible, contract, "registry_record_mismatch",
            ))
        cached = self._cached(model_id)
        if cached is not None:
            self._revalidate_cached(model_id, cached, contract)
            return cached.session
        model_bytes = self._get_model_bytes(record.r2_key, contract.artifact_sha256)
        session = self._create_session(model_bytes)
        self._cache_session(model_id, session, contract, record.name, record.version)
        return session

    def load_registered_model(
        self,
        model_id: str,
        requested: ContractVersions | None = None,
    ) -> ort.InferenceSession:
        """Load a manifest-registered model for route-level inference."""
        resolution = self._resolve(model_id, requested)
        if resolution.contract is None or resolution.state is not ContractState.available:
            raise InferenceContractError(resolution)
        contract = resolution.contract
        cached = self._cached(model_id)
        if cached is not None:
            self._revalidate_cached(model_id, cached, contract)
            return cached.session
        try:
            model_bytes = self._get_model_bytes(contract.artifact_key, contract.artifact_sha256)
        except (FileNotFoundError, RuntimeError) as exc:
            raise InferenceContractError(ContractResolution(
                ContractState.unavailable, contract, "weights_unavailable",
            )) from exc
        session = self._create_session(model_bytes)
        self._cache_session(
            model_id, session, contract, contract.model_id, contract.versions.model_version,
        )
        return session

    def artifact_available(self, model_id: str) -> bool:
        """Return whether the manifest artifact exists and matches its digest."""
        contract = self._resolve(model_id).contract
        if contract is None or self._cache_dir is None:
            return False
        path = Path(self._cache_dir) / contract.artifact_key
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == contract.artifact_sha256

    def run_registered_inference(
        self,
        model_id: str,
        input_data: Mapping[str, np.ndarray],
        requested: ContractVersions | None = None,
    ) -> dict[str, Any]:
        """Run a real registered artifact and return state plus provenance."""
        resolution = self._resolve(model_id, requested)
        if resolution.contract is None or resolution.state is not ContractState.available:
            raise InferenceContractError(resolution)
        session = self.load_registered_model(model_id, requested)
        started = time.perf_counter()
        try:
            with telemetry_span("model.inference", {"model": model_id}):
                outputs = run_session(session, input_data, resolution.contract)
        finally:
            record_model_inference(model_id, resolution.state.value, time.perf_counter() - started)
        return {
            "state": resolution.state.value,
            "outputs": outputs,
            "provenance": build_provenance(
                resolution.contract,
                state=resolution.state,
                input_data=input_data,
            ),
            "model_version": f"{resolution.contract.model_id}:{resolution.contract.versions.model_version}",
        }

    def run_inference(self, model_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Run DB-registered inference with canonical provenance."""
        record = self._get_model_metadata(model_id)
        resolution = self._resolve(record.name)
        if resolution.contract is None:
            raise InferenceContractError(resolution)
        session = self.load_model(model_id)
        started = time.perf_counter()
        try:
            with telemetry_span("model.inference", {"model": record.name}):
                outputs = run_session(session, input_data, resolution.contract)
        finally:
            record_model_inference(record.name, resolution.state.value, time.perf_counter() - started)
        return {
            "state": resolution.state.value,
            "outputs": outputs,
            "provenance": build_provenance(
                resolution.contract,
                state=resolution.state,
                input_data=input_data,
            ),
            "model_version": f"{record.name}:{record.version}",
        }

    def validate_input(
        self,
        model_id: str,
        input_data: Mapping[str, np.ndarray],
        requested: ContractVersions | None = None,
    ) -> ContractResolution:
        """Validate a provided tensor payload before state-based abstention."""
        resolution = self._resolve(model_id, requested)
        if resolution.contract is None or resolution.state is ContractState.incompatible:
            raise InferenceContractError(resolution)
        validate_inputs(input_data, resolution.contract)
        return resolution

    def unload_model(self, model_id: str) -> bool:
        """Unload one cached model."""
        with self._lock:
            return self._cache.pop(model_id, None) is not None

    def unload_idle_models(self, timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_S) -> list[str]:
        """Unload models that have exceeded the idle timeout."""
        cutoff = now_ms() - timeout_seconds * 1000
        with self._lock:
            unloaded = [
                model_id for model_id, cached in self._cache.items()
                if cached.last_used_ms < cutoff
            ]
            for model_id in unloaded:
                self._cache.pop(model_id)
            return unloaded

    @staticmethod
    def _run_session(session: ort.InferenceSession, input_data: Mapping[str, Any], contract: InferenceContract | None) -> dict[str, Any]:
        return run_session(session, input_data, contract)

    @staticmethod
    def _validate_inputs(input_data: Mapping[str, np.ndarray], contract: InferenceContract) -> None:
        validate_inputs(input_data, contract)

    @staticmethod
    def _provenance(contract: InferenceContract, *, state: ContractState = ContractState.available, input_data: Mapping[str, np.ndarray] | None = None) -> dict[str, str | int]:
        return build_provenance(contract, state=state, input_data=input_data)


__all__ = ["DEFAULT_IDLE_TIMEOUT_S", "ModelServing"]
