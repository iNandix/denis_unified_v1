"""
Chunk Deduplicator - Detect and handle similar/duplicate chunks.

Features:
- Semantic similarity detection (using embeddings or simple text comparison)
- Merge similar chunks
- Group related chunks
- Keep most relevant version
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class DuplicateGroup:
    """Group of similar chunks."""

    representative_id: str
    chunk_ids: List[str] = field(default_factory=list)
    similarity_scores: Dict[str, float] = field(default_factory=dict)
    merged_text: str = ""
    source_urls: List[str] = field(default_factory=list)


@dataclass
class DeduplicationResult:
    """Result of deduplication."""

    original_count: int
    unique_count: int
    groups: List[DuplicateGroup]
    removed_ids: List[str] = field(default_factory=list)
    merged_chunks: List[Dict[str, Any]] = field(default_factory=list)


class ChunkDeduplicator:
    """Detect and handle duplicate chunks."""

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold

    def find_duplicates(self, chunks: List[Any]) -> List[DuplicateGroup]:
        """Find groups of similar chunks."""
        groups = []
        processed: Set[str] = set()

        for i, chunk in enumerate(chunks):
            if chunk.id in processed:
                continue

            similar = [chunk]
            similar_scores = {chunk.id: 1.0}
            processed.add(chunk.id)

            for j, other in enumerate(chunks):
                if i == j or other.id in processed:
                    continue

                sim = self._compute_similarity(chunk.text, other.text)

                if sim >= self.similarity_threshold:
                    similar.append(other)
                    similar_scores[other.id] = sim
                    processed.add(other.id)

            if len(similar) > 1:
                group = DuplicateGroup(
                    representative_id=chunk.id,
                    chunk_ids=[s.id for s in similar],
                    similarity_scores=similar_scores,
                )
                groups.append(group)

        return groups

    def deduplicate(self, chunks: List[Any]) -> DeduplicationResult:
        """Remove duplicate chunks, keeping most relevant."""
        if not chunks:
            return DeduplicationResult(0, 0, [])

        groups = self.find_duplicates(chunks)

        # Determine which chunks to keep
        keep_ids: Set[str] = set()
        removed_ids: List[str] = []
        merged_chunks: List[Dict[str, Any]] = []

        for group in groups:
            # Keep the one with highest relevance score
            group_chunks = [c for c in chunks if c.id in group.chunk_ids]
            best = max(group_chunks, key=lambda c: c.relevance_score)

            keep_ids.add(best.id)
            removed_ids.extend([cid for cid in group.chunk_ids if cid != best.id])

            # Merge information from duplicates
            merged_text = self._merge_texts([c.text for c in group_chunks])
            merged_chunks.append(
                {
                    "original_id": best.id,
                    "merged_text": merged_text,
                    "source_count": len(group.chunk_ids),
                    "similar_ids": group.chunk_ids,
                }
            )

        # Add non-duplicate chunks
        unique_chunks = [c for c in chunks if c.id not in processed_set(groups)]
        keep_ids.update(c.id for c in unique_chunks)

        return DeduplicationResult(
            original_count=len(chunks),
            unique_count=len(keep_ids),
            groups=groups,
            removed_ids=removed_ids,
            merged_chunks=merged_chunks,
        )

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """Compute similarity between two texts."""
        # Normalize
        t1 = self._normalize(text1)
        t2 = self._normalize(text2)

        if not t1 or not t2:
            return 0.0

        # Jaccard similarity on words
        words1 = set(t1.split())
        words2 = set(t2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        jaccard = len(intersection) / len(union) if union else 0.0

        # Bonus for exact substring match
        if t1 in t2 or t2 in t1:
            jaccard = max(jaccard, 0.9)

        # Character n-gram similarity
        ngram_sim = self._ngram_similarity(t1, t2)

        # Combine
        return (jaccard * 0.6) + (ngram_sim * 0.4)

    def _ngram_similarity(self, text1: str, text2: str, n: int = 3) -> float:
        """Compute n-gram similarity."""

        def get_ngrams(text: str) -> Set[str]:
            return set(text[i : i + n] for i in range(len(text) - n + 1))

        ngrams1 = get_ngrams(text1)
        ngrams2 = get_ngrams(text2)

        if not ngrams1 or not ngrams2:
            return 0.0

        intersection = ngrams1 & ngrams2
        union = ngrams1 | ngrams2

        return len(intersection) / len(union) if union else 0.0

    def _normalize(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase
        text = text.lower()
        # Remove punctuation
        text = re.sub(r"[^\w\s]", " ", text)
        # Remove extra whitespace
        text = " ".join(text.split())
        return text

    def _merge_texts(self, texts: List[str]) -> str:
        """Merge multiple texts intelligently."""
        if len(texts) == 1:
            return texts[0]

        # Take the longest as base
        base = max(texts, key=len)

        # Extract unique sentences from others
        base_sentences = set(self._split_sentences(base))

        merged = list(base_sentences)

        for text in texts[1:]:
            sentences = self._split_sentences(text)
            for sent in sentences:
                if sent not in base_sentences:
                    merged.append(sent)

        # Reconstruct
        return " ".join(merged)

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if s.strip()]

    def group_by_topic(self, chunks: List[Any]) -> Dict[str, List[Any]]:
        """Group chunks by detected topic."""
        from denis_unified_v1.actions.chunk_classifier import ChunkClassifier

        classifier = ChunkClassifier()
        groups: Dict[str, List[Any]] = {}

        for chunk in chunks:
            metadata = classifier.classify(chunk)
            topic = metadata.topic or "general"

            if topic not in groups:
                groups[topic] = []
            groups[topic].append(chunk)

        return groups

    def group_by_category(self, chunks: List[Any]) -> Dict[str, List[Any]]:
        """Group chunks by category."""
        from denis_unified_v1.actions.chunk_classifier import (
            ChunkClassifier,
            ChunkCategory,
        )

        classifier = ChunkClassifier()
        groups: Dict[str, List[Any]] = {}

        for chunk in chunks:
            metadata = classifier.classify(chunk)
            category = metadata.category.value

            if category not in groups:
                groups[category] = []
            groups[category].append(chunk)

        return groups


def processed_set(groups: List[DuplicateGroup]) -> Set[str]:
    """Get all processed chunk IDs from groups."""
    result = set()
    for group in groups:
        result.update(group.chunk_ids)
    return result


def deduplicate_chunks(
    chunks: List[Any], threshold: float = 0.85
) -> DeduplicationResult:
    """Convenience function."""
    dedup = ChunkDeduplicator(similarity_threshold=threshold)
    return dedup.deduplicate(chunks)
