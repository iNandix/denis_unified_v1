"""Episodic memory storage."""

from __future__ import annotations

import json
from typing import Any

from denis_unified_v1.memory.backends import Neo4jBackend, RedisBackend, utc_now


class EpisodicMemory:
    def __init__(self, redis_backend: RedisBackend, neo4j_backend: Neo4jBackend) -> None:
        self.redis = redis_backend
        self.neo4j = neo4j_backend

    def save_conversation(
        self,
        *,
        conv_id: str,
        user_id: str,
        messages: list[dict[str, Any]],
        outcome: str,
    ) -> dict[str, Any]:
        event = {
            "conv_id": conv_id,
            "user_id": user_id,
            "messages": messages,
            "outcome": outcome,
            "timestamp_utc": utc_now(),
        }
        self.redis.hset_json("memory:episodic:conversations", conv_id, event)
        neo4j_ok = self.neo4j.write_cypher(
            """
            MERGE (c:Conversation {conv_id:$conv_id})
            SET c.user_id = $user_id,
                c.messages = $messages_json,
                c.outcome = $outcome,
                c.timestamp_utc = $timestamp_utc
            """,
            conv_id=conv_id,
            user_id=user_id,
            messages_json=json.dumps(messages, ensure_ascii=True),
            outcome=outcome,
            timestamp_utc=event["timestamp_utc"],
        )
        return {"status": "ok", "conv_id": conv_id, "neo4j_written": neo4j_ok}

    def get_conversation(self, conv_id: str) -> dict[str, Any] | None:
        return self.redis.hget_json("memory:episodic:conversations", conv_id)
