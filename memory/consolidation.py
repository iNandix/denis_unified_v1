"""Memory consolidation engine - aggregates episodic memories into semantic knowledge."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from denis_unified_v1.feature_flags import load_feature_flags
from denis_unified_v1.memory.backends import Neo4jBackend, RedisBackend, utc_now
from denis_unified_v1.observability.metrics import memory_consolidations
from denis_unified_v1.observability.tracing import get_tracer

tracer = get_tracer()


class MemoryConsolidator:
    """Consolidates episodic memories into semantic facts and preferences."""

    def __init__(
        self,
        redis: RedisBackend,
        neo4j: Neo4jBackend,
        llm_client: Any = None,
    ):
        self.redis = redis
        self.neo4j = neo4j
        self.llm_client = llm_client
        self.flags = load_feature_flags()

    async def consolidate_daily(self, days_back: int = 1) -> dict[str, Any]:
        """Consolidate memories from the last N days."""
        with tracer.start_as_current_span("memory.consolidate_daily") as span:
            span.set_attribute("days_back", days_back)

            if not self.flags.phase9_memory_consolidation_enabled:
                return {"status": "disabled", "reason": "consolidation_flag_off"}

            start_time = datetime.now(timezone.utc) - timedelta(days=days_back)
            start_iso = start_time.isoformat()

            # Get all conversations from Redis
            all_convs = self.redis.hgetall_json("memory:episodic:conversations")
            recent_convs = [
                conv
                for conv in all_convs.values()
                if conv.get("timestamp_utc", "") >= start_iso
            ]

            span.set_attribute("conversations_found", len(recent_convs))

            if not recent_convs:
                return {"status": "ok", "conversations_processed": 0, "facts_extracted": 0}

            # Group by user
            by_user: dict[str, list[dict]] = defaultdict(list)
            for conv in recent_convs:
                user_id = conv.get("user_id", "unknown")
                by_user[user_id].append(conv)

            total_facts = 0
            total_preferences = 0

            for user_id, convs in by_user.items():
                facts, prefs = await self._extract_knowledge(user_id, convs)
                total_facts += len(facts)
                total_preferences += len(prefs)

                # Store facts
                for fact in facts:
                    await self._store_fact(user_id, fact)

                # Store preferences
                for pref in prefs:
                    await self._store_preference(user_id, pref)

            # Apply retention policy
            await self._apply_retention()

            memory_consolidations.labels(status="success").inc()

            return {
                "status": "ok",
                "conversations_processed": len(recent_convs),
                "users_processed": len(by_user),
                "facts_extracted": total_facts,
                "preferences_extracted": total_preferences,
                "timestamp_utc": utc_now(),
            }

    async def _extract_knowledge(
        self, user_id: str, conversations: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Extract facts and preferences from conversations."""
        facts = []
        preferences = []

        # Heuristic extraction (can be enhanced with LLM)
        for conv in conversations:
            messages = conv.get("messages", [])
            for msg in messages:
                if msg.get("role") != "user":
                    continue

                content = msg.get("content", "").lower()

                # Extract preferences
                pref_patterns = [
                    (r"me gusta (.+)", "likes"),
                    (r"prefiero (.+)", "prefers"),
                    (r"no me gusta (.+)", "dislikes"),
                    (r"odio (.+)", "hates"),
                    (r"amo (.+)", "loves"),
                ]

                for pattern, pref_type in pref_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        preferences.append({
                            "type": pref_type,
                            "value": match.strip(),
                            "confidence": 0.7,
                            "source_conv": conv.get("conv_id"),
                        })

                # Extract facts
                fact_patterns = [
                    (r"vivo en (.+)", "location"),
                    (r"trabajo en (.+)", "occupation"),
                    (r"mi nombre es (.+)", "name"),
                    (r"tengo (.+) años", "age"),
                    (r"uso (.+)", "uses_tool"),
                ]

                for pattern, fact_type in fact_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        facts.append({
                            "type": fact_type,
                            "value": match.strip(),
                            "confidence": 0.8,
                            "source_conv": conv.get("conv_id"),
                        })

        # Deduplicate and merge confidence
        facts = self._deduplicate_knowledge(facts)
        preferences = self._deduplicate_knowledge(preferences)

        return facts, preferences

    def _deduplicate_knowledge(self, items: list[dict]) -> list[dict]:
        """Deduplicate and merge confidence scores."""
        by_key: dict[str, dict] = {}

        for item in items:
            key = f"{item['type']}:{item['value']}"
            if key in by_key:
                # Merge confidence (average)
                existing = by_key[key]
                existing["confidence"] = (
                    existing["confidence"] + item["confidence"]
                ) / 2
                existing["occurrences"] = existing.get("occurrences", 1) + 1
            else:
                item["occurrences"] = 1
                by_key[key] = item

        return list(by_key.values())

    async def _store_fact(self, user_id: str, fact: dict) -> None:
        """Store a fact in Redis and Neo4j."""
        fact_id = hashlib.sha256(
            f"{user_id}:{fact['type']}:{fact['value']}".encode()
        ).hexdigest()[:16]

        fact_data = {
            "fact_id": fact_id,
            "user_id": user_id,
            "type": fact["type"],
            "value": fact["value"],
            "confidence": fact["confidence"],
            "occurrences": fact.get("occurrences", 1),
            "source_conv": fact.get("source_conv"),
            "created_utc": utc_now(),
        }

        # Store in Redis
        self.redis.hset_json("memory:semantic:facts", fact_id, fact_data)

        # Store in Neo4j
        self.neo4j.write_cypher(
            """
            MERGE (u:User {user_id: $user_id})
            MERGE (f:Fact {fact_id: $fact_id})
            SET f.type = $type,
                f.value = $value,
                f.confidence = $confidence,
                f.occurrences = $occurrences,
                f.created_utc = $created_utc
            MERGE (u)-[:HAS_FACT]->(f)
            """,
            user_id=user_id,
            fact_id=fact_id,
            type=fact["type"],
            value=fact["value"],
            confidence=fact["confidence"],
            occurrences=fact.get("occurrences", 1),
            created_utc=fact_data["created_utc"],
        )

    async def _store_preference(self, user_id: str, pref: dict) -> None:
        """Store a preference in Redis and Neo4j."""
        pref_id = hashlib.sha256(
            f"{user_id}:{pref['type']}:{pref['value']}".encode()
        ).hexdigest()[:16]

        pref_data = {
            "pref_id": pref_id,
            "user_id": user_id,
            "type": pref["type"],
            "value": pref["value"],
            "confidence": pref["confidence"],
            "occurrences": pref.get("occurrences", 1),
            "source_conv": pref.get("source_conv"),
            "created_utc": utc_now(),
        }

        # Store in Redis
        self.redis.hset_json("memory:semantic:preferences", pref_id, pref_data)

        # Store in Neo4j
        self.neo4j.write_cypher(
            """
            MERGE (u:User {user_id: $user_id})
            MERGE (p:Preference {pref_id: $pref_id})
            SET p.type = $type,
                p.value = $value,
                p.confidence = $confidence,
                p.occurrences = $occurrences,
                p.created_utc = $created_utc
            MERGE (u)-[:HAS_PREFERENCE]->(p)
            """,
            user_id=user_id,
            pref_id=pref_id,
            type=pref["type"],
            value=pref["value"],
            confidence=pref["confidence"],
            occurrences=pref.get("occurrences", 1),
            created_utc=pref_data["created_utc"],
        )

    async def _apply_retention(self) -> None:
        """Apply retention policy - archive old episodic memories."""
        retention_days = self.flags.phase9_memory_retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()

        # Get all conversations
        all_convs = self.redis.hgetall_json("memory:episodic:conversations")

        archived_count = 0
        for conv_id, conv in all_convs.items():
            if conv.get("timestamp_utc", "") < cutoff_iso:
                # Archive to Neo4j with archived flag
                self.neo4j.write_cypher(
                    """
                    MATCH (c:Conversation {conv_id: $conv_id})
                    SET c.archived = true, c.archived_utc = $archived_utc
                    """,
                    conv_id=conv_id,
                    archived_utc=utc_now(),
                )
                archived_count += 1

        # Note: We keep in Redis for now, could delete if needed


async def run_consolidation_job(
    redis: RedisBackend, neo4j: Neo4jBackend, interval_minutes: int = 60
) -> None:
    """Background job that runs consolidation periodically."""
    consolidator = MemoryConsolidator(redis, neo4j)

    while True:
        try:
            result = await consolidator.consolidate_daily(days_back=1)
            print(f"[Consolidation] {result}")
        except Exception as e:
            print(f"[Consolidation Error] {e}")
            memory_consolidations.labels(status="error").inc()

        await asyncio.sleep(interval_minutes * 60)
