"""IndexingBus: ingest durable knowledge into vectorstore (fail-open)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from denis_unified_v1.indexing.chunker import chunk_text
from denis_unified_v1.indexing.redaction_gate import redact_for_indexing, safe_snippet
from denis_unified_v1.vectorstore.qdrant_client import get_vectorstore, sha256_text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class IndexPiece:
    kind: str
    title: str
    content: str
    tags: list[str]
    source: str
    trace_id: str | None = None
    conversation_id: str | None = None
    provider: str | None = None
    language: str | None = None
    file_path: str | None = None
    section: str | None = None
    extra: dict[str, Any] | None = None


class IndexingBus:
    def __init__(self) -> None:
        self.enabled = (os.getenv("INDEXING_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    def upsert_piece(self, piece: IndexPiece) -> dict[str, Any]:
        """Index a piece. Returns a small status dict, never raises."""
        if not self.enabled:
            return {"ok": False, "status": "disabled"}

        try:
            safe_text, safety = redact_for_indexing(piece.content)

            # Dedupe by canonicalized safe_text hash.
            h = sha256_text(safe_text)
            parent_id = h

            # If PII risk high, index only a snippet (still redacted).
            if safety.pii_risk == "high":
                safe_text = safe_snippet(safe_text, max_chars=400)

            chunks = chunk_text(
                safe_text,
                parent_id=parent_id,
                target_chars=int(os.getenv("INDEX_CHUNK_TARGET_CHARS", "2400")),
                overlap_chars=int(os.getenv("INDEX_CHUNK_OVERLAP_CHARS", "200")),
                max_chunks=int(os.getenv("INDEX_CHUNK_MAX_CHUNKS", "64")),
            )
            if not chunks:
                chunks = []

            store = get_vectorstore()
            collection = (os.getenv("QDRANT_COLLECTION_DEFAULT") or "denis_chunks_v1").strip()

            point_ids: list[str] = []
            for ch in (chunks or []):
                payload = {
                    "kind": piece.kind,
                    "title": piece.title,
                    "tags": list(piece.tags or []),
                    "source": piece.source,
                    "created_at": _utc_now_iso(),
                    "updated_at": _utc_now_iso(),
                    "trace_id": piece.trace_id,
                    "conversation_id": piece.conversation_id,
                    "provider": piece.provider,
                    "language": piece.language,
                    "file_path": piece.file_path,
                    "section": piece.section,
                    "parent_id": parent_id,
                    "chunk_index": int(ch.chunk_index),
                    "hash_sha256": h,
                    "safety": {"redacted": True, "pii_risk": safety.pii_risk},
                }
                if piece.extra:
                    payload["extra"] = dict(piece.extra)
                pid = store.upsert_text(
                    collection=collection,
                    text=ch.text,
                    payload=payload,
                    point_id=f"{parent_id}:{ch.chunk_index}",
                    dedupe_hash=h,
                )
                point_ids.append(pid)

            return {"ok": True, "status": "upserted", "hash_sha256": h, "points": point_ids}
        except Exception:
            return {"ok": False, "status": "degraded"}


_BUS: IndexingBus | None = None


def get_indexing_bus() -> IndexingBus:
    global _BUS
    if _BUS is None:
        _BUS = IndexingBus()
    return _BUS

