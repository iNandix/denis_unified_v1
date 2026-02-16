"""
Context Manager - Graph-centric episode/turn persistence.

Provides context retrieval and persistence for conversations.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """Conversation episode."""

    session_id: str
    start_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_ts: Optional[datetime] = None
    user_id: Optional[str] = None
    channel: Optional[str] = None


@dataclass
class Turn:
    """Single turn in conversation."""

    turn_id: str
    episode_session_id: str
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    intent: Optional[str] = None
    text: Optional[str] = None
    tool_used: Optional[str] = None
    tool_result: Optional[dict] = None
    confidence: Optional[float] = None
    error: Optional[str] = None


def create_episode(
    session_id: str,
    user_id: Optional[str] = None,
    channel: Optional[str] = None,
) -> Episode:
    """Create new episode in graph."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    if not flags.context_uses_graph:
        return Episode(session_id=session_id, user_id=user_id, channel=channel)

    driver = _get_neo4j_driver()
    if not driver:
        return Episode(session_id=session_id, user_id=user_id, channel=channel)

    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (e:Episode {session_id: $session_id})
                SET e.start_ts = coalesce(e.start_ts, datetime()),
                    e.user_id = coalesce($user_id, e.user_id),
                    e.channel = coalesce($channel, e.channel)
            """,
                session_id=session_id,
                user_id=user_id,
                channel=channel,
            )
    except Exception as e:
        logger.warning(f"Failed to create episode: {e}")

    return Episode(session_id=session_id, user_id=user_id, channel=channel)


def close_episode(session_id: str) -> bool:
    """Close episode in graph."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    if not flags.context_uses_graph:
        return True

    driver = _get_neo4j_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            session.run(
                """
                MATCH (e:Episode {session_id: $session_id})
                SET e.end_ts = datetime()
            """,
                session_id=session_id,
            )
        return True
    except Exception as e:
        logger.warning(f"Failed to close episode: {e}")
        return False


def add_turn(
    turn_id: str,
    session_id: str,
    intent: Optional[str] = None,
    text: Optional[str] = None,
    tool_used: Optional[str] = None,
    tool_result: Optional[dict] = None,
    confidence: Optional[float] = None,
    error: Optional[str] = None,
) -> Turn:
    """Add turn to episode."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    turn = Turn(
        turn_id=turn_id,
        episode_session_id=session_id,
        intent=intent,
        text=text,
        tool_used=tool_used,
        tool_result=tool_result,
        confidence=confidence,
        error=error,
    )

    if not flags.context_uses_graph:
        return turn

    driver = _get_neo4j_driver()
    if not driver:
        return turn

    try:
        with driver.session() as session:
            session.run(
                """
                MATCH (e:Episode {session_id: $session_id})
                MERGE (e)-[:HAS_TURN]->(t:Turn {turn_id: $turn_id})
                SET t.intent = $intent,
                    t.text = $text,
                    t.tool_used = $tool_used,
                    t.tool_result = $tool_result,
                    t.confidence = $confidence,
                    t.error = $error,
                    t.ts = datetime()
            """,
                session_id=session_id,
                turn_id=turn_id,
                intent=intent,
                text=text,
                tool_used=tool_used,
                tool_result=str(tool_result) if tool_result else None,
                confidence=confidence,
                error=error,
            )
    except Exception as e:
        logger.warning(f"Failed to add turn: {e}")

    return turn


def get_episode_context(session_id: str, max_turns: int = 10) -> dict[str, Any]:
    """Get recent context from episode."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    if not flags.context_uses_graph:
        return {"session_id": session_id, "turns": []}

    driver = _get_neo4j_driver()
    if not driver:
        return {"session_id": session_id, "turns": []}

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (e:Episode {session_id: $session_id})-[:HAS_TURN]->(t:Turn)
                RETURN t.turn_id as turn_id, t.intent as intent, t.text as text,
                       t.tool_used as tool_used, t.ts as ts
                ORDER BY t.ts DESC
                LIMIT $max_turns
            """,
                session_id=session_id,
                max_turns=max_turns,
            )

            turns = [
                {
                    "turn_id": r["turn_id"],
                    "intent": r["intent"],
                    "text": r["text"],
                    "tool": r["tool_used"],
                    "ts": str(r["ts"]) if r["ts"] else None,
                }
                for r in result
            ]
            return {"session_id": session_id, "turns": list(reversed(turns))}
    except Exception as e:
        logger.warning(f"Failed to get episode context: {e}")
        return {"session_id": session_id, "turns": []}


def link_memory_to_episode(session_id: str, memory_id: str) -> bool:
    """Link memory chunk to episode."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    if not flags.context_uses_graph or not flags.memory_uses_graph:
        return False

    driver = _get_neo4j_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            session.run(
                """
                MATCH (e:Episode {session_id: $session_id})
                MATCH (m:MemoryChunk {chunk_id: $memory_id})
                MERGE (e)-[:HAS_MEMORY]->(m)
            """,
                session_id=session_id,
                memory_id=memory_id,
            )
        return True
    except Exception as e:
        logger.warning(f"Failed to link memory: {e}")
        return False
