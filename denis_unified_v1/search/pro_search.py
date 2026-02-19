"""Semantic "pro search" backed by Qdrant vector memory (fail-open).

This is intentionally small and stable for RAG.
Do not confuse with the graph-centric PRO_SEARCH skill toolchain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from denis_unified_v1.vectorstore.qdrant_client import get_vectorstore
from denis_unified_v1.indexing.redaction_gate import safe_snippet


@dataclass(frozen=True)
class ProSearchHit:
    chunk_id: str
    title: str
    tags: list[str]
    kind: str
    score: float
    snippet_redacted: str
    provenance: dict[str, Any]


def search(
    *,
    query: str,
    tags: list[str] | None = None,
    kind: str | None = None,
    limit: int = 8,
    language: str | None = None,
    source: str | None = None,
) -> tuple[list[ProSearchHit], dict[str, Any]]:
    """Search vector memory and return hits + a warning dict (maybe empty)."""
    store = get_vectorstore()
    filters: dict[str, Any] = {}
    if kind:
        filters["kind"] = kind
    if language:
        filters["language"] = language
    if source:
        filters["source"] = source

    hits = store.search(query=query, limit=max(1, int(limit)), filters=filters or None)

    # Tags filter is applied in-process to keep qdrant filter simple.
    out: list[ProSearchHit] = []
    for h in hits:
        payload = dict(h.payload or {})
        pt_tags = payload.get("tags") or []
        if tags:
            if not isinstance(pt_tags, list) or not set(tags).issubset(set(pt_tags)):
                continue
        text = payload.get("text_redacted") or ""
        out.append(
            ProSearchHit(
                chunk_id=str(payload.get("id") or h.id),
                title=str(payload.get("title") or ""),
                tags=list(pt_tags) if isinstance(pt_tags, list) else [],
                kind=str(payload.get("kind") or ""),
                score=float(h.score),
                snippet_redacted=safe_snippet(str(text), max_chars=280),
                provenance={
                    "source": payload.get("source"),
                    "hash_sha256": payload.get("hash_sha256"),
                    "file_path": payload.get("file_path"),
                    "section": payload.get("section"),
                    "parent_id": payload.get("parent_id"),
                    "chunk_index": payload.get("chunk_index"),
                },
            )
        )

    out.sort(key=lambda x: x.score, reverse=True)
    warning: dict[str, Any] = {}
    if store.enabled and store.fail_count > 0:
        warning = {"code": "vectorstore_degraded", "msg": "qdrant_failed_over"}
    return out[: max(1, int(limit))], warning

