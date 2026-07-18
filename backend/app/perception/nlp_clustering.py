"""Duplicate/near-duplicate clustering for citizen reports (T21).

Clusters reports by embedding cosine similarity. Uses FAISS when available
(``faiss-cpu>=1.8.0`` is in requirements.txt); falls back to a pure-Python
cosine similarity when FAISS is not installed or for small test sets.

The embedder is injectable: in production, pass a real sentence-encoder
``embed_fn``; in tests, pass a bag-of-words embedder or let the default
hash-based fallback handle it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.perception.nlp_types import ProcessedReport


@dataclass(slots=True, frozen=True)
class _Embedding:
    """An embedding vector with its source report ID."""

    report_id: str
    vector: list[float]


class DuplicateClusterer:
    """Cluster near-duplicate reports by embedding similarity.

    ``embed_fn`` is injectable. When ``None``, a deterministic hash-based
    bag-of-words embedder is used (sufficient for small test sets, not for
    production scale).
    """

    def __init__(
        self,
        embed_fn: Callable[[str], list[float]] | None = None,
        threshold: float = 0.85,
    ) -> None:
        self._embed_fn = embed_fn
        self._threshold = threshold

    def cluster(
        self,
        reports: Sequence[ProcessedReport],
        threshold: float | None = None,
    ) -> list[list[str]]:
        """Return clusters as lists of report IDs."""
        if len(reports) < 2:
            return [[r.report_id] for r in reports]
        thr = threshold if threshold is not None else self._threshold
        embeddings = self._embed_reports(reports)
        return self._cluster_with_faiss(embeddings, thr)

    # ── Embedding ────────────────────────────────────────────────────────

    def _embed_reports(
        self,
        reports: Sequence[ProcessedReport],
    ) -> list[_Embedding]:
        if self._embed_fn is not None:
            return [
                _Embedding(r.report_id, self._embed_fn(r.redacted_text))
                for r in reports
            ]
        return [
            _Embedding(r.report_id, self._hash_bow(r.redacted_text))
            for r in reports
        ]

    @staticmethod
    def _hash_bow(text: str) -> list[float]:
        """Deterministic 64-dim hash-based bag-of-words embedding.

        Sufficient for duplicate detection on small test sets. Production
        should inject a real sentence encoder via ``embed_fn``.
        """
        import re

        tokens = re.findall(r"[a-zà-ÿ\u0900-\u097f]{2,}", text.lower())
        vec = [0.0] * 64
        for token in tokens:
            vec[hash(token) % 64] += 1.0
        return vec

    # ── Clustering backends ─────────────────────────────────────────────

    def _cluster_with_faiss(
        self,
        embeddings: list[_Embedding],
        threshold: float,
    ) -> list[list[str]]:
        try:
            import faiss  # type: ignore[import-untyped]
            import numpy as np
        except ImportError:
            return self._cluster_python(embeddings, threshold)

        matrix = np.array([e.vector for e in embeddings], dtype="float32")
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        k = len(embeddings)
        sim, idx = index.search(matrix, k)
        return self._group_clusters(embeddings, sim.tolist(), idx.tolist(), threshold)

    def _cluster_python(
        self,
        embeddings: list[_Embedding],
        threshold: float,
    ) -> list[list[str]]:
        """Pure-Python cosine similarity fallback."""
        n = len(embeddings)
        sim: list[list[float]] = []
        for i in range(n):
            row = [
                self._cosine(embeddings[i].vector, embeddings[j].vector)
                for j in range(n)
            ]
            sim.append(row)
        idx = [list(range(n)) for _ in range(n)]
        return self._group_clusters(embeddings, sim, idx, threshold)

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    @staticmethod
    def _group_clusters(
        embeddings: list[_Embedding],
        sim: list[list[float]],
        idx: list[list[int]],
        threshold: float,
    ) -> list[list[str]]:
        """Union-find clustering: two reports cluster when cosine >= threshold."""
        n = len(embeddings)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            for j_pos, j in enumerate(idx[i]):
                if j == i or j < 0:
                    continue
                if sim[i][j_pos] >= threshold:
                    union(i, j)

        groups: dict[int, list[str]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(embeddings[i].report_id)
        return list(groups.values())


__all__: list[Any] = ["DuplicateClusterer"]
