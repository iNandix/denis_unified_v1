"""Unified memory manager (episodic, semantic, procedural, working)."""

from __future__ import annotations

from typing import Any

from denis_unified_v1.memory.backends import Neo4jBackend, RedisBackend
from denis_unified_v1.memory.episodic import EpisodicMemory
from denis_unified_v1.memory.procedural import ProceduralMemory
from denis_unified_v1.memory.semantic import SemanticMemory
from denis_unified_v1.memory.working import WorkingMemory


class MemoryManager:
    def __init__(self) -> None:
        self.redis = RedisBackend()
        self.neo4j = Neo4jBackend()
        self.episodic = EpisodicMemory(self.redis, self.neo4j)
        self.semantic = SemanticMemory(self.redis, self.neo4j)
        self.procedural = ProceduralMemory(self.redis)
        self.working = WorkingMemory(self.redis)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "components": {
                "episodic": True,
                "semantic": True,
                "procedural": True,
                "working": True,
            },
        }


def build_memory_manager() -> MemoryManager:
    return MemoryManager()
