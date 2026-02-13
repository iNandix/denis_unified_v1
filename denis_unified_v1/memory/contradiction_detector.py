"""Contradiction detector - identifies conflicting facts and preferences."""

from __future__ import annotations

import hashlib
from typing import Any

from denis_unified_v1.memory.backends import Neo4jBackend, RedisBackend, utc_now
from denis_unified_v1.observability.tracing import get_tracer

tracer = get_tracer()


class ContradictionDetector:
    """Detects and manages contradictions in memory."""

    def __init__(self, redis: RedisBackend, neo4j: Neo4jBackend):
        self.redis = redis
        self.neo4j = neo4j

    async def detect_contradictions(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """Detect contradictions in facts and preferences."""
        with tracer.start_as_current_span("memory.detect_contradictions") as span:
            contradictions = []

            # Detect fact contradictions
            fact_contradictions = await self._detect_fact_contradictions(user_id)
            contradictions.extend(fact_contradictions)

            # Detect preference contradictions
            pref_contradictions = await self._detect_preference_contradictions(user_id)
            contradictions.extend(pref_contradictions)

            span.set_attribute("contradictions_found", len(contradictions))

            return contradictions

    async def _detect_fact_contradictions(self, user_id: str | None) -> list[dict]:
        """Detect contradicting facts (same type, different values)."""
        all_facts = self.redis.hgetall_json("memory:semantic:facts")

        # Filter by user if specified
        if user_id:
            all_facts = {
                k: v for k, v in all_facts.items() if v.get("user_id") == user_id
            }

        # Group by (user_id, type)
        by_user_type: dict[str, list[dict]] = {}
        for fact in all_facts.values():
            key = f"{fact['user_id']}:{fact['type']}"
            if key not in by_user_type:
                by_user_type[key] = []
            by_user_type[key].append(fact)

        contradictions = []

        # Check for conflicts within each group
        for key, facts in by_user_type.items():
            if len(facts) < 2:
                continue

            # Sort by confidence descending
            facts_sorted = sorted(facts, key=lambda x: x.get("confidence", 0), reverse=True)

            # Compare each pair
            for i, fact1 in enumerate(facts_sorted):
                for fact2 in facts_sorted[i + 1 :]:
                    if fact1["value"] != fact2["value"]:
                        # Found contradiction
                        contradiction = {
                            "type": "fact_conflict",
                            "user_id": fact1["user_id"],
                            "fact_type": fact1["type"],
                            "fact1_id": fact1["fact_id"],
                            "fact1_value": fact1["value"],
                            "fact1_confidence": fact1["confidence"],
                            "fact2_id": fact2["fact_id"],
                            "fact2_value": fact2["value"],
                            "fact2_confidence": fact2["confidence"],
                            "detected_utc": utc_now(),
                            "status": "unresolved",
                        }

                        contradictions.append(contradiction)

                        # Store in Neo4j
                        await self._store_contradiction(contradiction)

        return contradictions

    async def _detect_preference_contradictions(self, user_id: str | None) -> list[dict]:
        """Detect contradicting preferences (likes vs dislikes)."""
        all_prefs = self.redis.hgetall_json("memory:semantic:preferences")

        # Filter by user if specified
        if user_id:
            all_prefs = {
                k: v for k, v in all_prefs.items() if v.get("user_id") == user_id
            }

        # Group by (user_id, value)
        by_user_value: dict[str, list[dict]] = {}
        for pref in all_prefs.values():
            key = f"{pref['user_id']}:{pref['value']}"
            if key not in by_user_value:
                by_user_value[key] = []
            by_user_value[key].append(pref)

        contradictions = []

        # Check for opposing preferences
        opposing_types = [
            ("likes", "dislikes"),
            ("likes", "hates"),
            ("loves", "hates"),
            ("prefers", "dislikes"),
        ]

        for key, prefs in by_user_value.items():
            if len(prefs) < 2:
                continue

            for pref1 in prefs:
                for pref2 in prefs:
                    if pref1["pref_id"] == pref2["pref_id"]:
                        continue

                    # Check if types are opposing
                    type_pair = (pref1["type"], pref2["type"])
                    if type_pair in opposing_types or tuple(reversed(type_pair)) in opposing_types:
                        contradiction = {
                            "type": "preference_conflict",
                            "user_id": pref1["user_id"],
                            "value": pref1["value"],
                            "pref1_id": pref1["pref_id"],
                            "pref1_type": pref1["type"],
                            "pref1_confidence": pref1["confidence"],
                            "pref2_id": pref2["pref_id"],
                            "pref2_type": pref2["type"],
                            "pref2_confidence": pref2["confidence"],
                            "detected_utc": utc_now(),
                            "status": "unresolved",
                        }

                        contradictions.append(contradiction)

                        # Store in Neo4j
                        await self._store_contradiction(contradiction)

        return contradictions

    async def _store_contradiction(self, contradiction: dict) -> None:
        """Store contradiction in Neo4j."""
        contradiction_id = hashlib.sha256(
            f"{contradiction['type']}:{contradiction.get('fact1_id') or contradiction.get('pref1_id')}:{contradiction.get('fact2_id') or contradiction.get('pref2_id')}".encode()
        ).hexdigest()[:16]

        contradiction["contradiction_id"] = contradiction_id

        # Store in Redis
        self.redis.hset_json("memory:contradictions", contradiction_id, contradiction)

        # Store in Neo4j with CONTRADICTS relationship
        if contradiction["type"] == "fact_conflict":
            self.neo4j.write_cypher(
                """
                MATCH (f1:Fact {fact_id: $fact1_id})
                MATCH (f2:Fact {fact_id: $fact2_id})
                MERGE (c:Contradiction {contradiction_id: $contradiction_id})
                SET c.type = $type,
                    c.detected_utc = $detected_utc,
                    c.status = $status
                MERGE (f1)-[:CONTRADICTS {via: $contradiction_id}]->(f2)
                MERGE (c)-[:INVOLVES]->(f1)
                MERGE (c)-[:INVOLVES]->(f2)
                """,
                fact1_id=contradiction["fact1_id"],
                fact2_id=contradiction["fact2_id"],
                contradiction_id=contradiction_id,
                type=contradiction["type"],
                detected_utc=contradiction["detected_utc"],
                status=contradiction["status"],
            )
        else:  # preference_conflict
            self.neo4j.write_cypher(
                """
                MATCH (p1:Preference {pref_id: $pref1_id})
                MATCH (p2:Preference {pref_id: $pref2_id})
                MERGE (c:Contradiction {contradiction_id: $contradiction_id})
                SET c.type = $type,
                    c.detected_utc = $detected_utc,
                    c.status = $status
                MERGE (p1)-[:CONTRADICTS {via: $contradiction_id}]->(p2)
                MERGE (c)-[:INVOLVES]->(p1)
                MERGE (c)-[:INVOLVES]->(p2)
                """,
                pref1_id=contradiction["pref1_id"],
                pref2_id=contradiction["pref2_id"],
                contradiction_id=contradiction_id,
                type=contradiction["type"],
                detected_utc=contradiction["detected_utc"],
                status=contradiction["status"],
            )

    async def resolve_contradiction(
        self, contradiction_id: str, resolution: str, winner_id: str | None = None
    ) -> dict[str, Any]:
        """Resolve a contradiction by marking winner or merging."""
        contradiction = self.redis.hget_json("memory:contradictions", contradiction_id)

        if not contradiction:
            return {"status": "error", "reason": "contradiction_not_found"}

        contradiction["status"] = "resolved"
        contradiction["resolution"] = resolution
        contradiction["resolved_utc"] = utc_now()

        if winner_id:
            contradiction["winner_id"] = winner_id

            # Lower confidence of loser
            if contradiction["type"] == "fact_conflict":
                loser_id = (
                    contradiction["fact2_id"]
                    if winner_id == contradiction["fact1_id"]
                    else contradiction["fact1_id"]
                )
                loser = self.redis.hget_json("memory:semantic:facts", loser_id)
                if loser:
                    loser["confidence"] *= 0.5  # Reduce confidence
                    self.redis.hset_json("memory:semantic:facts", loser_id, loser)

            elif contradiction["type"] == "preference_conflict":
                loser_id = (
                    contradiction["pref2_id"]
                    if winner_id == contradiction["pref1_id"]
                    else contradiction["pref1_id"]
                )
                loser = self.redis.hget_json("memory:semantic:preferences", loser_id)
                if loser:
                    loser["confidence"] *= 0.5
                    self.redis.hset_json("memory:semantic:preferences", loser_id, loser)

        # Update in Redis
        self.redis.hset_json("memory:contradictions", contradiction_id, contradiction)

        # Update in Neo4j
        self.neo4j.write_cypher(
            """
            MATCH (c:Contradiction {contradiction_id: $contradiction_id})
            SET c.status = $status,
                c.resolution = $resolution,
                c.resolved_utc = $resolved_utc,
                c.winner_id = $winner_id
            """,
            contradiction_id=contradiction_id,
            status="resolved",
            resolution=resolution,
            resolved_utc=contradiction["resolved_utc"],
            winner_id=winner_id,
        )

        return {"status": "ok", "contradiction_id": contradiction_id}

    async def list_contradictions(
        self, user_id: str | None = None, status: str | None = None
    ) -> list[dict]:
        """List all contradictions, optionally filtered."""
        all_contradictions = self.redis.hgetall_json("memory:contradictions")

        result = list(all_contradictions.values())

        # Filter by user_id
        if user_id:
            result = [c for c in result if c.get("user_id") == user_id]

        # Filter by status
        if status:
            result = [c for c in result if c.get("status") == status]

        return result
