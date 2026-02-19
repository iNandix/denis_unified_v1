"""Chunking utilities for vector indexing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    parent_id: str
    text: str


def chunk_text(
    text: str,
    *,
    parent_id: str,
    target_chars: int = 2400,
    overlap_chars: int = 200,
    max_chunks: int = 64,
) -> list[TextChunk]:
    """Split text into overlapping chunks (char-based approximation).

    We keep this dependency-free and deterministic.
    """
    s = (text or "").strip()
    if not s:
        return []

    target_chars = max(200, int(target_chars))
    overlap_chars = max(0, int(overlap_chars))
    max_chunks = max(1, int(max_chunks))

    out: list[TextChunk] = []
    i = 0
    idx = 0
    n = len(s)
    while i < n and idx < max_chunks:
        end = min(n, i + target_chars)
        chunk = s[i:end]
        out.append(TextChunk(chunk_index=idx, parent_id=parent_id, text=chunk))
        idx += 1
        if end >= n:
            break
        i = max(0, end - overlap_chars)
    return out

