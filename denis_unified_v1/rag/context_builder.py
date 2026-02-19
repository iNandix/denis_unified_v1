"""RAG Context Builder (fail-open).

Produces a small, redacted context pack for providers, plus citations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from denis_unified_v1.search.pro_search import search as pro_search


@dataclass(frozen=True)
class RagContextPack:
    query: str
    chunks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    warning: dict[str, Any] | None = None


def build_rag_context_pack(
    *,
    user_text: str,
    trace_id: str | None,
    conversation_id: str | None,
) -> RagContextPack:
    enabled = (os.getenv("RAG_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        return RagContextPack(query="", chunks=[], citations=[], warning={"code": "disabled"})

    query = (user_text or "").strip()
    if not query:
        return RagContextPack(query="", chunks=[], citations=[], warning={"code": "empty_query"})

    k = int(os.getenv("RAG_TOPK", "8"))
    kind = os.getenv("RAG_KIND_FILTER") or None
    hits, warn = pro_search(query=query, kind=kind, limit=k)

    chunks: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    for h in hits:
        chunks.append(
            {
                "chunk_id": h.chunk_id,
                "title": h.title,
                "score": h.score,
                "snippet_redacted": h.snippet_redacted,
                "tags": h.tags,
                "kind": h.kind,
                "provenance": h.provenance,
            }
        )
        citations.append(
            {
                "chunk_id": h.chunk_id,
                "source": h.provenance.get("source"),
                "hash_sha256": h.provenance.get("hash_sha256"),
            }
        )

    warning = warn or None
    return RagContextPack(query=query, chunks=chunks, citations=citations, warning=warning)

