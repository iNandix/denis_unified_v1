"""Unified memory manager (episodic, semantic, procedural, working)."""

from __future__ import annotations

from typing import Any

from denis_unified_v1.memory.backends import Neo4jBackend, RedisBackend
from denis_unified_v1.memory.consolidation import MemoryConsolidator
from denis_unified_v1.memory.contradiction_detector import ContradictionDetector
from denis_unified_v1.memory.episodic import EpisodicMemory
from denis_unified_v1.memory.procedural import ProceduralMemory
from denis_unified_v1.memory.retrieval import MemoryRetrieval
from denis_unified_v1.memory.semantic import SemanticMemory
from denis_unified_v1.memory.working import WorkingMemory


class MemoryManager:
    """Unified memory manager with advanced features."""

    def __init__(self) -> None:
        self.redis = RedisBackend()
        self.neo4j = Neo4jBackend()
        
        # Core memory types
        self.episodic = EpisodicMemory(self.redis, self.neo4j)
        self.semantic = SemanticMemory(self.redis, self.neo4j)
        self.procedural = ProceduralMemory(self.redis)
        self.working = WorkingMemory(self.redis)
        
        # Advanced features
        self.consolidator = MemoryConsolidator(self.redis, self.neo4j)
        self.contradiction_detector = ContradictionDetector(self.redis, self.neo4j)
        self.retrieval = MemoryRetrieval(self.redis, self.neo4j)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "components": {
                "episodic": True,
                "semantic": True,
                "procedural": True,
                "working": True,
                "consolidator": True,
                "contradiction_detector": True,
                "retrieval": True,
            },
            "backends": {
                "redis": self.redis._client_or_none() is not None,
                "neo4j": self.neo4j._driver_or_none() is not None,
            },
        }


def build_memory_manager() -> MemoryManager:
    return MemoryManager()
