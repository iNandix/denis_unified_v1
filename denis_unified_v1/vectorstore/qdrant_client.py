"""Qdrant vector memory client (fail-open).

This module is intentionally dependency-light:
- Uses `qdrant_client` if installed and reachable.
- Falls back to an in-memory store with deterministic embeddings for tests/dev.

No secrets are logged.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    raw = (text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _canonicalize(text: str) -> str:
    # Stable canonicalization for dedupe hashing.
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    # Collapse excessive whitespace.
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    return s


def _deterministic_vector(text: str, *, dim: int) -> list[float]:
    """Deterministic pseudo-embedding from sha256 digest (no external model)."""
    h = hashlib.sha256((text or "").encode("utf-8", errors="ignore")).digest()
    # Expand digest to `dim` floats in [-1, 1].
    out: list[float] = []
    b = bytearray(h)
    while len(out) < dim:
        # Re-hash the growing buffer to extend deterministically.
        b = bytearray(hashlib.sha256(bytes(b)).digest())
        for v in b:
            out.append((int(v) / 127.5) - 1.0)
            if len(out) >= dim:
                break
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    # Small, safe cosine similarity (no numpy).
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


@dataclass(frozen=True)
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any]


@dataclass(frozen=True)
class VectorHit:
    id: str
    score: float
    payload: dict[str, Any]


class VectorStoreError(RuntimeError):
    pass


class QdrantVectorStore:
    """Thin wrapper with fail-open behavior.

    Env:
    - VECTORSTORE_ENABLED=1
    - QDRANT_URL (default http://127.0.0.1:6333)
    - QDRANT_API_KEY (optional)
    - QDRANT_COLLECTION_DEFAULT (default denis_chunks_v1)
    - QDRANT_VECTOR_SIZE (default 384)
    """

    def __init__(self) -> None:
        self.enabled = (os.getenv("VECTORSTORE_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        self.url = (os.getenv("QDRANT_URL") or "http://127.0.0.1:6333").strip()
        self.api_key = os.getenv("QDRANT_API_KEY") or None
        self.collection_default = (
            os.getenv("QDRANT_COLLECTION_DEFAULT") or "denis_chunks_v1"
        ).strip()
        try:
            self.vector_size = int(os.getenv("QDRANT_VECTOR_SIZE") or "384")
        except Exception:
            self.vector_size = 384

        self._client = None
        self._mock: dict[str, dict[str, VectorPoint]] = {}

        # Ops counters (best-effort, process-local).
        self.last_upsert_ts: str = ""
        self.upsert_count = 0
        self.search_count = 0
        self.fail_count = 0

    def _get_client(self):
        if not self.enabled:
            return None
        if self._client is not None:
            return self._client
        try:
            import qdrant_client  # type: ignore

            timeout_s = float(os.getenv("DENIS_QDRANT_TIMEOUT_S", "0.4"))
            # Ensure we never hang on network probes. qdrant_client uses httpx under the hood.
            self._client = qdrant_client.QdrantClient(
                url=self.url, api_key=self.api_key, timeout=timeout_s
            )
            return self._client
        except Exception:
            self._client = None
            return None

    def ensure_collection(self, *, collection: str | None = None) -> None:
        name = (collection or self.collection_default).strip()
        if not name:
            raise VectorStoreError("collection_required")
        client = self._get_client()
        if client is None:
            self._mock.setdefault(name, {})
            return
        try:
            from qdrant_client.http import models  # type: ignore

            # Create if missing (do not recreate).
            cols = client.get_collections()
            existing = {c.name for c in getattr(cols, "collections", [])}
            if name in existing:
                return
            client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception as exc:
            self.fail_count += 1
            # Fail-open: fallback to mock
            self._mock.setdefault(name, {})

    def upsert_text(
        self,
        *,
        collection: str | None = None,
        text: str,
        payload: dict[str, Any],
        point_id: str | None = None,
        dedupe_hash: str | None = None,
    ) -> str:
        """Upsert a single point. Returns point id.

        Dedupe:
        - If `dedupe_hash` provided, we store it as `hash_sha256` in payload and use it as idempotency key.
        - Caller should compute it from canonicalized content.
        """
        name = (collection or self.collection_default).strip()
        self.ensure_collection(collection=name)

        canon = _canonicalize(text)
        h = dedupe_hash or sha256_text(canon)
        pid = point_id or h  # deterministic id for dedupe

        vec = _deterministic_vector(canon, dim=self.vector_size)
        p = dict(payload or {})
        p.setdefault("hash_sha256", h)
        p.setdefault("created_at", _utc_now_iso())
        p["updated_at"] = _utc_now_iso()
        p.setdefault("id", pid)

        client = self._get_client()
        try:
            if client is None:
                self._mock.setdefault(name, {})[pid] = VectorPoint(
                    id=pid, vector=vec, payload={**p, "text_redacted": canon}
                )
            else:
                from qdrant_client.http import models  # type: ignore

                client.upsert(
                    collection_name=name,
                    points=[
                        models.PointStruct(
                            id=pid,
                            vector=vec,
                            payload={**p, "text_redacted": canon},
                        )
                    ],
                )
            self.upsert_count += 1
            self.last_upsert_ts = _utc_now_iso()
            return pid
        except Exception:
            self.fail_count += 1
            # Fail-open: store in mock
            self._mock.setdefault(name, {})[pid] = VectorPoint(
                id=pid, vector=vec, payload={**p, "text_redacted": canon}
            )
            self.upsert_count += 1
            self.last_upsert_ts = _utc_now_iso()
            return pid

    def search(
        self,
        *,
        collection: str | None = None,
        query: str,
        limit: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        name = (collection or self.collection_default).strip()
        self.ensure_collection(collection=name)
        qv = _deterministic_vector(_canonicalize(query), dim=self.vector_size)
        self.search_count += 1

        client = self._get_client()
        if client is None:
            hits: list[VectorHit] = []
            for pid, pt in (self._mock.get(name) or {}).items():
                if not _payload_matches(pt.payload, filters):
                    continue
                hits.append(
                    VectorHit(
                        id=pid,
                        score=_cosine(qv, pt.vector),
                        payload=dict(pt.payload),
                    )
                )
            hits.sort(key=lambda h: h.score, reverse=True)
            return hits[: max(1, int(limit))]

        try:
            from qdrant_client.http import models  # type: ignore

            qfilter = _build_qdrant_filter(filters)
            res = client.search(
                collection_name=name,
                query_vector=qv,
                limit=max(1, int(limit)),
                query_filter=qfilter,
            )
            out: list[VectorHit] = []
            for r in res:
                out.append(
                    VectorHit(
                        id=str(r.id),
                        score=float(getattr(r, "score", 0.0) or 0.0),
                        payload=dict(getattr(r, "payload", {}) or {}),
                    )
                )
            out.sort(key=lambda h: h.score, reverse=True)
            return out
        except Exception:
            self.fail_count += 1
            # Fail-open: fallback to mock scoring.
            hits: list[VectorHit] = []
            for pid, pt in (self._mock.get(name) or {}).items():
                if not _payload_matches(pt.payload, filters):
                    continue
                hits.append(
                    VectorHit(
                        id=pid,
                        score=_cosine(qv, pt.vector),
                        payload=dict(pt.payload),
                    )
                )
            hits.sort(key=lambda h: h.score, reverse=True)
            return hits[: max(1, int(limit))]


def _payload_matches(payload: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    for k, v in filters.items():
        if v is None:
            continue
        pv = payload.get(k)
        if isinstance(v, (list, tuple, set)):
            if pv not in v:
                return False
        else:
            if pv != v:
                return False
    return True


def _build_qdrant_filter(filters: dict[str, Any] | None):
    if not filters:
        return None
    try:
        from qdrant_client.http import models  # type: ignore

        must = []
        for k, v in filters.items():
            if v is None:
                continue
            if isinstance(v, (list, tuple, set)):
                must.append(models.FieldCondition(key=k, match=models.MatchAny(any=list(v))))
            else:
                must.append(models.FieldCondition(key=k, match=models.MatchValue(value=v)))
        return models.Filter(must=must)
    except Exception:
        return None


_STORE: QdrantVectorStore | None = None


def get_vectorstore() -> QdrantVectorStore:
    global _STORE
    if _STORE is None:
        _STORE = QdrantVectorStore()
    return _STORE


def reset_vectorstore_for_tests() -> None:
    global _STORE
    _STORE = None
