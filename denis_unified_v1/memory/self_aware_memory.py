import re
import time
from typing import Dict, List, Any, Optional

from denis_unified_v1.metacognitive.hooks import metacognitive_trace

class ImportanceScorer:
    def score(self, memory: Dict[str, Any]) -> float:
        recency = time.time() - memory.get("timestamp", 0)
        frequency = memory.get("access_count", 0)
        semantic = len(memory.get("content", "")) / 100  # Simple proxy
        return (1 / (1 + recency / 86400)) * 0.4 + (frequency / 10) * 0.3 + semantic * 0.3

class DecayDetector:
    def detect(self, memory: Dict[str, Any]) -> bool:
        last_access = memory.get("last_access", 0)
        return time.time() - last_access > 30 * 24 * 3600  # 30 days

class Consolidator:
    def consolidate(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Merge similar memories
        content = " ".join([m.get("content", "") for m in memories])
        return {"content": content[:500], "timestamp": time.time(), "consolidated": True}

class ConflictResolver:
    def resolve(self, conflicts: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Simple: keep the most recent
        return max(conflicts, key=lambda x: x.get("timestamp", 0))

class KnowledgeExtractor:
    def extract(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        content = memory.get("content", "")
        keywords = content.split()[:5]  # Simple extraction
        return {"keywords": keywords, "summary": content[:100]}

class SelfNarrativeBuilder:
    def build(self, memories: List[Dict[str, Any]]) -> str:
        narrative = " ".join([m.get("content", "") for m in memories[:3]])
        return f"Narrative: {narrative}"

def process_memory(memories: List[Dict[str, Any]]) -> Dict[str, Any]:
    scorer = ImportanceScorer()
    scores = [scorer.score(m) for m in memories]
    detector = DecayDetector()
    decayed = [m for m in memories if detector.detect(m)]
    consolidator = Consolidator()
    consolidated = consolidator.consolidate(decayed) if decayed else {}
    resolver = ConflictResolver()
    resolved = resolver.resolve(memories) if len(memories) > 1 else memories[0] if memories else {}
    extractor = KnowledgeExtractor()
    knowledge = extractor.extract(resolved)
    builder = SelfNarrativeBuilder()
    narrative = builder.build(memories)
    return {
        "scores": scores,
        "decayed": len(decayed),
        "consolidated": consolidated,
        "resolved": resolved,
        "knowledge": knowledge,
        "narrative": narrative
    }


class SelfAwareMemoryTier:
    """Memory tier with metacognitive self-awareness for operations."""

    def __init__(self, memory_backend: Any):
        self.backend = memory_backend

    async def store(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> Dict[str, Any]:
        """Store with metacognitive tracking."""
        start_time = time.time()
        try:
            result = await self.backend.store(key, value, ttl_seconds)
            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "success",
                "key": key,
                "latency_ms": latency_ms,
                "stored": True,
            }
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "error",
                "key": key,
                "latency_ms": latency_ms,
                "error": str(e),
            }

    async def retrieve(self, key: str) -> Dict[str, Any]:
        """Retrieve with metacognitive tracking."""
        start_time = time.time()
        try:
            result = await self.backend.retrieve(key)
            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "success",
                "key": key,
                "value": result,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "error",
                "key": key,
                "latency_ms": latency_ms,
                "error": str(e),
            }

    async def consolidate(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Consolidate memory with metacognitive tracking."""
        start_time = time.time()
        try:
            result = await self.backend.consolidate()
            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "success",
                "latency_ms": latency_ms,
                "consolidated": result,
            }
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "error",
                "latency_ms": latency_ms,
                "error": str(e),
            }

    def get_status(self) -> Dict[str, Any]:
        """Metacognitive status of memory tier."""
        return {
            "enabled": True,
            "backend_available": self.backend is not None,
            "status": "healthy",
        }


def build_self_aware_memory_tier() -> SelfAwareMemoryTier:
    """Build self-aware memory tier with fail-open."""
    try:
        from denis_unified_v1.memory.backends import RedisBackend
        backend = RedisBackend()
        return SelfAwareMemoryTier(backend)
    except Exception as e:
        # Fail-open: return with no-op backend
        class NoOpBackend:
            async def store(self, key, value, ttl):
                return True

            async def retrieve(self, key):
                return None

            async def consolidate(self):
                return []

        return SelfAwareMemoryTier(NoOpBackend())
