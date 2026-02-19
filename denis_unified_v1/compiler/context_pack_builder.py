"""Context Pack Builder for Compiler - retrieves Graph + Qdrant context.

This module builds the context_pack that gets sent to the ChatRoom compiler.
It aggregates:
- Graph SSoT state (Intent/Plan/Tasks/Runs summary)
- Vectorstore chunks (topK relevant snippets)

No secrets, no raw text, no CoT - only hashes and redacted snippets.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextPack:
    """Context pack for compiler."""

    graph_entities: list[dict[str, Any]] = field(default_factory=list)
    vectorstore_chunks: list[dict[str, Any]] = field(default_factory=list)
    graph_hash: str = ""
    chunks_hash: str = ""
    combined_hash: str = ""

    def to_compiler_input(self) -> str:
        """Format as input to the compiler LLM."""
        parts = []

        if self.graph_entities:
            parts.append("## Graph Context (SSoT):")
            for e in self.graph_entities[:10]:
                parts.append(
                    f"- {e.get('type', '?')}: {e.get('name', e.get('id', '?'))} [{e.get('status', 'unknown')}]"
                )

        if self.vectorstore_chunks:
            parts.append("\n## Knowledge Base:")
            for c in self.vectorstore_chunks[:5]:
                snippet = c.get("snippet_redacted", "")[:100]
                parts.append(f"- [{c.get('score', 0):.2f}] {snippet}...")

        return "\n".join(parts) if parts else "(No context available)"


def _sha256(data: str) -> str:
    """Compute SHA256 hash."""
    return hashlib.sha256((data or "").encode("utf-8", errors="ignore")).hexdigest()


def _sha256_short(data: str) -> str:
    return _sha256(data)[:16]


async def build_context_pack(
    input_text: str,
    max_graph_entities: int = 40,
    max_chunks: int = 12,
    enable_graph: bool = True,
    enable_vectorstore: bool = True,
) -> ContextPack:
    """
    Build context pack from Graph + Vectorstore.

    Args:
        input_text: User input to search against
        max_graph_entities: Max entities to retrieve from Graph
        max_chunks: Max chunks to retrieve from vectorstore
        enable_graph: Whether to query Graph
        enable_vectorstore: Whether to query vectorstore

    Returns:
        ContextPack with retrieved context
    """
    pack = ContextPack()

    if enable_graph:
        pack.graph_entities = await _retrieve_graph_entities(max_graph_entities)
        pack.graph_hash = _sha256_short(json.dumps(pack.graph_entities, sort_keys=True))

    if enable_vectorstore:
        pack.vectorstore_chunks = await _retrieve_vectorstore_chunks(input_text, max_chunks)
        pack.chunks_hash = _sha256_short(json.dumps(pack.vectorstore_chunks, sort_keys=True))

    pack.combined_hash = _sha256_short(pack.graph_hash + pack.chunks_hash)

    return pack


async def _retrieve_graph_entities(limit: int = 40) -> list[dict[str, Any]]:
    """Retrieve relevant entities from Graph (SSoT)."""
    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        graph = get_graph_client()

        if not graph.enabled:
            logger.debug("Graph disabled, skipping")
            return []

        driver = graph._get_driver()
        if not driver:
            logger.debug("No Graph driver, skipping")
            return []

        query = """
        MATCH (n)
        WHERE n.last_active IS NOT NULL
        OPTIONAL MATCH (n)-[r:DEPENDS_ON]->(dep)
        RETURN labels(n)[0] as type, n.id as id, n.name as name,
               n.last_active as last_active, n.status as status,
               count(r) as dep_count
        ORDER BY n.last_active DESC
        LIMIT $limit
        """

        with driver.session() as session:
            result = session.run(query, limit=limit)
            entities = []
            for record in result:
                entities.append(
                    {
                        "type": record["type"],
                        "id": record.get("id", ""),
                        "name": record.get("name", ""),
                        "status": record.get("status", ""),
                        "dep_count": record.get("dep_count", 0),
                        "hash": _sha256_short(str(record)),
                    }
                )
            return entities

    except Exception as e:
        logger.warning(f"Graph retrieval failed: {e}")
        return []


async def _retrieve_vectorstore_chunks(query: str, limit: int = 12) -> list[dict[str, Any]]:
    """Retrieve relevant chunks from Qdrant vectorstore."""
    try:
        from denis_unified_v1.search.pro_search import search

        hits, warning = search(
            query=query,
            limit=limit,
        )

        chunks = []
        for hit in hits:
            chunks.append(
                {
                    "chunk_id": hit.chunk_id,
                    "title": hit.title,
                    "tags": hit.tags,
                    "kind": hit.kind,
                    "score": hit.score,
                    "snippet_redacted": hit.snippet_redacted[:200],
                    "provenance": hit.provenance,
                    "hash": _sha256_short(hit.snippet_redacted),
                }
            )

        return chunks

    except Exception as e:
        logger.warning(f"Vectorstore retrieval failed: {e}")
        return []


def get_context_pack_sync(
    input_text: str,
    max_graph_entities: int = 40,
    max_chunks: int = 12,
) -> ContextPack:
    """Synchronous wrapper for build_context_pack."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = loop.create_task(
                build_context_pack(input_text, max_graph_entities, max_chunks)
            )
            return future.result(timeout=10)
        return loop.run_until_complete(
            build_context_pack(input_text, max_graph_entities, max_chunks)
        )
    except RuntimeError:
        return asyncio.run(build_context_pack(input_text, max_graph_entities, max_chunks))
