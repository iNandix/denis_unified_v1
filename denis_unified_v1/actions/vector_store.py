"""
Qdrant Vector Store - Semantic search for chunks.

Provides:
- Vector embeddings storage
- Semantic similarity search
- Collection management
- Filters and pagination
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import numpy as np


@dataclass
class VectorChunk:
    """A chunk stored in vector DB."""

    id: str
    text: str
    vector: List[float]
    payload: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class SearchResult:
    """Vector search result."""

    id: str
    text: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)


class QdrantStore:
    """Vector store using Qdrant (or mock for now)."""

    def __init__(
        self,
        collection_name: str = "denis_chunks",
        vector_size: int = 384,
        url: str = None,
        api_key: str = None,
    ):
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")

        self._client = None
        self._mock_mode = True  # Start with mock for testing

    def _get_client(self):
        """Get Qdrant client (lazy init)."""
        if self._mock_mode:
            return None

        try:
            from qdrant_client import QdrantClient

            if self._client is None:
                self._client = QdrantClient(url=self.url, api_key=self.api_key)
            return self._client
        except ImportError:
            self._mock_mode = True
            return None

    def create_collection(self, recreate: bool = False) -> bool:
        """Create collection."""
        client = self._get_client()

        if self._mock_mode or client is None:
            self._mock_data: Dict[str, VectorChunk] = {}
            return True

        try:
            from qdrant_client.models import Distance, VectorParams

            if recreate:
                client.delete_collection(self.collection_name)

            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )
            return True
        except Exception as e:
            print(f"Create collection error: {e}")
            return False

    def upsert(self, chunks: List[VectorChunk]) -> bool:
        """Insert or update chunks."""
        client = self._get_client()

        if self._mock_mode or client is None:
            for chunk in chunks:
                self._mock_data[chunk.id] = chunk
            return True

        try:
            from qdrant_client.models import PointStruct

            points = [
                PointStruct(
                    id=chunk.id,
                    vector=chunk.vector,
                    payload={"text": chunk.text, **chunk.payload},
                )
                for chunk in chunks
            ]

            client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            return True
        except Exception as e:
            print(f"Upsert error: {e}")
            return False

    def search(
        self,
        query_vector: List[float] = None,
        query_text: str = None,
        limit: int = 5,
        filter_conditions: Dict[str, Any] = None,
    ) -> List[SearchResult]:
        """Search for similar chunks."""
        client = self._get_client()

        if self._mock_mode or client is None:
            return self._mock_search(query_text, limit)

        try:
            from qdrant_client.models import Filter, FieldCondition, Match

            query_filter = None
            if filter_conditions:
                conditions = []
                for key, value in filter_conditions.items():
                    conditions.append(FieldCondition(key=key, match=Match(value=value)))
                query_filter = Filter(must=conditions)

            if query_vector:
                results = client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    query_filter=query_filter,
                )
            else:
                results = client.search(
                    collection_name=self.collection_name,
                    query_text=query_text,
                    limit=limit,
                    query_filter=query_filter,
                )

            return [
                SearchResult(
                    id=r.id,
                    text=r.payload.get("text", ""),
                    score=r.score,
                    payload=r.payload,
                )
                for r in results
            ]
        except Exception as e:
            print(f"Search error: {e}")
            return []

    def _mock_search(self, query_text: str, limit: int) -> List[SearchResult]:
        """Mock search using text similarity."""
        if not query_text:
            return []

        query_words = set(query_text.lower().split())

        results = []
        for chunk in self._mock_data.values():
            text_words = set(chunk.text.lower().split())
            if not text_words:
                continue

            # Simple Jaccard
            intersection = query_words & text_words
            union = query_words | text_words
            score = len(intersection) / len(union) if union else 0.0

            results.append(
                SearchResult(
                    id=chunk.id,
                    text=chunk.text,
                    score=score,
                    payload=chunk.payload,
                )
            )

        # Sort by score
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def delete(self, ids: List[str]) -> bool:
        """Delete chunks by ID."""
        client = self._get_client()

        if self._mock_mode or client is None:
            for id_ in ids:
                self._mock_data.pop(id_, None)
            return True

        try:
            client.delete(
                collection_name=self.collection_name,
                points_selector=ids,
            )
            return True
        except Exception as e:
            print(f"Delete error: {e}")
            return False

    def get_by_id(self, id: str) -> Optional[VectorChunk]:
        """Get chunk by ID."""
        client = self._get_client()

        if self._mock_mode or client is None:
            chunk = self._mock_data.get(id)
            return chunk

        try:
            results = client.retrieve(
                collection_name=self.collection_name,
                ids=[id],
            )
            if results:
                r = results[0]
                return VectorChunk(
                    id=r.id,
                    text=r.payload.get("text", ""),
                    vector=r.vector,
                    payload=r.payload,
                )
        except Exception as e:
            print(f"Get error: {e}")

        return None


class EmbeddingGenerator:
    """Generate embeddings for text."""

    def __init__(self, model: str = "sentence-transformers"):
        self.model = model
        self._client = None
        self._mock_mode = True

    def _get_client(self):
        """Get embedding model client."""
        if self._mock_mode:
            return None

        try:
            from sentence_transformers import SentenceTransformer

            if self._client is None:
                self._client = SentenceTransformer(self.model)
            return self._client
        except ImportError:
            self._mock_mode = True
            return None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        client = self._get_client()

        if self._mock_mode or client is None:
            # Generate pseudo-embeddings (for testing)
            return self._mock_embed(texts)

        try:
            embeddings = client.encode(texts)
            return embeddings.tolist()
        except Exception as e:
            print(f"Embed error: {e}")
            return self._mock_embed(texts)

    def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a query."""
        embeddings = self.embed_texts([query])
        return embeddings[0] if embeddings else []

    def _mock_embed(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings based on text hash."""
        embeddings = []
        for text in texts:
            # Simple hash-based pseudo-embedding
            hash_val = hash(text) % 10000
            vec = np.random.randn(384)
            vec = vec / np.linalg.norm(vec)  # Normalize
            # Mix in hash
            vec[0] = hash_val / 10000.0
            embeddings.append(vec.tolist())
        return embeddings


class VectorStoreManager:
    """Manage vector store operations with Neo4j integration."""

    def __init__(self):
        self.store = QdrantStore()
        self.embedder = EmbeddingGenerator()

    def index_chunks(
        self,
        chunks: List[Any],
        collection: str = "denis_chunks",
    ) -> int:
        """Index chunks in vector store."""
        self.store.collection_name = collection
        self.store.create_collection(recreate=False)

        texts = [c.text for c in chunks]
        vectors = self.embedder.embed_texts(texts)

        vector_chunks = []
        for chunk, vector in zip(chunks, vectors):
            vector_chunks.append(
                VectorChunk(
                    id=chunk.id,
                    text=chunk.text,
                    vector=vector,
                    payload={
                        "source_url": chunk.source_url,
                        "source_title": chunk.source_title,
                        "relevance_score": chunk.relevance_score,
                        "category": getattr(
                            getattr(chunk, "metadata", None), "category", "unknown"
                        ),
                        "topic": getattr(
                            getattr(chunk, "metadata", None), "topic", "general"
                        ),
                        "indexed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )

        self.store.upsert(vector_chunks)
        return len(vector_chunks)

    def semantic_search(
        self,
        query: str,
        collection: str = "denis_chunks",
        limit: int = 5,
        filter_by: Dict[str, Any] = None,
    ) -> List[SearchResult]:
        """Semantic search."""
        self.store.collection_name = collection
        query_vector = self.embedder.embed_query(query)

        return self.store.search(
            query_vector=query_vector,
            limit=limit,
            filter_conditions=filter_by,
        )

    def find_related(
        self,
        chunk_id: str,
        collection: str = "denis_chunks",
        limit: int = 5,
    ) -> List[SearchResult]:
        """Find related chunks."""
        chunk = self.store.get_by_id(chunk_id)
        if not chunk:
            return []

        return self.store.search(
            query_vector=chunk.vector,
            limit=limit + 1,  # +1 because it will include itself
        )


# Convenience functions
def create_vector_store(
    collection: str = "denis_chunks",
    vector_size: int = 384,
) -> QdrantStore:
    """Create a vector store."""
    store = QdrantStore(collection_name=collection, vector_size=vector_size)
    store.create_collection()
    return store


def index_for_semantic_search(
    chunks: List[Any],
    collection: str = "denis_chunks",
) -> int:
    """Index chunks for semantic search."""
    manager = VectorStoreManager()
    return manager.index_chunks(chunks, collection)


def semantic_search(
    query: str,
    collection: str = "denis_chunks",
    limit: int = 5,
) -> List[SearchResult]:
    """Semantic search convenience function."""
    manager = VectorStoreManager()
    return manager.semantic_search(query, collection, limit)
