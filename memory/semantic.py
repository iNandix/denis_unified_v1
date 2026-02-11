"""Semantic memory storage."""

from __future__ import annotations

from typing import Any

from denis_unified_v1.memory.backends import Neo4jBackend, RedisBackend, utc_now


class SemanticMemory:
    def __init__(self, redis_backend: RedisBackend, neo4j_backend: Neo4jBackend) -> None:
        self.redis = redis_backend
        self.neo4j = neo4j_backend

    def upsert_concept(
        self,
        *,
        concept_id: str,
        name: str,
        weight_delta: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = "memory:semantic:concepts"
        existing = self.redis.hget_json(key, concept_id) or {
            "concept_id": concept_id,
            "name": name,
            "weight": 0.0,
        }
        existing["name"] = name
        existing["weight"] = float(existing.get("weight", 0.0)) + float(weight_delta)
        existing["last_accessed_utc"] = utc_now()
        if metadata:
            existing["metadata"] = metadata
        self.redis.hset_json(key, concept_id, existing)

        neo4j_ok = self.neo4j.write_cypher(
            """
            MERGE (c:Concept {concept_id:$concept_id})
            SET c.name = $name,
                c.weight = coalesce(c.weight, 0.0) + $weight_delta,
                c.last_accessed_utc = $last_accessed_utc
            """,
            concept_id=concept_id,
            name=name,
            weight_delta=float(weight_delta),
            last_accessed_utc=existing["last_accessed_utc"],
        )
        return {"status": "ok", "concept_id": concept_id, "neo4j_written": neo4j_ok}

    def get_concept(self, concept_id: str) -> dict[str, Any] | None:
        return self.redis.hget_json("memory:semantic:concepts", concept_id)
