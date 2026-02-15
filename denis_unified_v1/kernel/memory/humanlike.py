"""
Denis Kernel - Humanlike Memory Module
=====================================
Provides humanlike memory: identity, narrative state, episodic memory, people/pets graph.

M1: Identity (stable, persistent)
M2: User autobiographical (durable facts)
M3: Episodic events (with context and outcome)
M4: Narrative State (cheap, updated every turn)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Type of memory."""

    IDENTITY = "identity"
    AUTOBIOGRAPHICAL = "autobiographical"
    EPISODIC = "episodic"
    NARRATIVE = "narrative"


@dataclass
class NarrativeState:
    """
    M4: Narrative State - cheap, updated every turn.
    Makes Denis "sound human" without large context.
    """

    # What thread is active
    active_thread: Optional[str] = None
    thread_summary: Optional[str] = None

    # Current concerns/worries
    current_worry: Optional[str] = None
    current_interest: Optional[str] = None

    # Follow-ups due
    pending_follow_ups: List[Dict[str, Any]] = field(default_factory=list)

    # Last update info
    last_update: Optional[str] = None
    last_update_ts: Optional[str] = None

    # Relationship tone
    tone: str = "neutral"  # neutral, concerned, playful, serious

    # Context for this session
    session_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_thread": self.active_thread,
            "thread_summary": self.thread_summary,
            "current_worry": self.current_worry,
            "current_interest": self.current_interest,
            "pending_follow_ups": self.pending_follow_ups,
            "last_update": self.last_update,
            "last_update_ts": self.last_update_ts,
            "tone": self.tone,
            "session_context": self.session_context,
        }


@dataclass
class Person:
    """M2: A person in user's life."""

    id: str
    name: str
    relationship: str  # "user", "partner", "friend", "family", "colleague", "pet"
    key_facts: List[str] = field(default_factory=list)
    recent_events: List[str] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    last_mentioned: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "relationship": self.relationship,
            "key_facts": self.key_facts,
            "recent_events": self.recent_events,
            "preferences": self.preferences,
            "last_mentioned": self.last_mentioned,
        }


@dataclass
class EpisodicEvent:
    """
    M3: An episodic event with context and outcome.
    Key for "do you remember last Wednesday..."
    """

    id: str
    timestamp: str
    topic: str
    summary: str
    participants: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, str]] = field(
        default_factory=list
    )  # [{"type": "link", "url": "..."}]
    outcome: Optional[str] = None  # "resolved", "pending", "blocked", "abandoned"
    status: str = "active"  # "active", "archived"
    embedding_key: Optional[str] = None  # For vector search

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "topic": self.topic,
            "summary": self.summary,
            "participants": self.participants,
            "artifacts": self.artifacts,
            "outcome": self.outcome,
            "status": self.status,
        }


class HumanlikeMemory:
    """
    Humanlike memory system with 4 layers.

    Provides:
    - Identity (M1): Who Denis is
    - Autobiographical (M2): Facts about user
    - Episodic (M3): Events with context
    - Narrative State (M4): Cheap, updated every turn
    """

    def __init__(self, redis_client=None, neo4j_driver=None):
        self.redis = redis_client
        self.neo4j = neo4j_driver

    # M1: Identity - stored in constitution/config
    def get_identity(self) -> Dict[str, Any]:
        """Get Denis identity (from config)."""
        # This would load from constitution
        return {
            "name": "Denis",
            "role": "AI companion",
            "tone": "warm but competent",
            "boundaries": ["no harmful advice", "respects privacy"],
        }

    # M2: Autobiographical - People/Pets Graph
    async def get_person(self, person_id: str) -> Optional[Person]:
        """Get a person from memory."""
        if not self.redis:
            return None
        key = f"denis:person:{person_id}"
        data = await self.redis.get(key)
        if not data:
            return None
        d = json.loads(data)
        return Person(**d)

    async def save_person(self, person: Person):
        """Save a person to memory."""
        if not self.redis:
            return
        key = f"denis:person:{person.id}"
        person.last_mentioned = datetime.now(timezone.utc).isoformat()
        await self.redis.set(key, json.dumps(person.to_dict()))

    async def search_people(self, query: str) -> List[Person]:
        """Search people by name or relationship."""
        if not self.redis:
            return []
        # Simple search - in production use vector or Neo4j
        keys = await self.redis.keys("denis:person:*")
        results = []
        for key in keys:
            data = await self.redis.get(key)
            if data:
                p = Person(**json.loads(data))
                if (
                    query.lower() in p.name.lower()
                    or query.lower() in p.relationship.lower()
                ):
                    results.append(p)
        return results

    # M3: Episodic Memory
    async def add_episode(self, event: EpisodicEvent):
        """Add an episodic event."""
        if not self.redis:
            return
        key = f"denis:episode:{event.id}"
        await self.redis.set(key, json.dumps(event.to_dict()))

        # Also index by topic for fast lookup
        topic_key = f"denis:episodes:topic:{event.topic}"
        await self.redis.lpush(topic_key, event.id)

        logger.info(f"Added episode: {event.topic} at {event.timestamp}")

    async def get_episode(self, episode_id: str) -> Optional[EpisodicEvent]:
        """Get an episode by ID."""
        if not self.redis:
            return None
        key = f"denis:episode:{episode_id}"
        data = await self.redis.get(key)
        if not data:
            return None
        d = json.loads(data)
        return EpisodicEvent(**d)

    async def get_episodes_by_topic(
        self, topic: str, limit: int = 5
    ) -> List[EpisodicEvent]:
        """Get recent episodes by topic."""
        if not self.redis:
            return []
        topic_key = f"denis:episodes:topic:{topic}"
        episode_ids = await self.redis.lrange(topic_key, 0, limit - 1)

        episodes = []
        for ep_id in episode_ids:
            ep = await self.get_episode(ep_id)
            if ep:
                episodes.append(ep)
        return episodes

    async def get_episodes_by_time_range(
        self, start_date: str, end_date: Optional[str] = None, limit: int = 10
    ) -> List[EpisodicEvent]:
        """Get episodes in a time range."""
        if not self.redis:
            return []
        # Simple: scan all episodes (in production use time-series index)
        keys = await self.redis.keys("denis:episode:*")

        episodes = []
        for key in keys[:50]:  # Limit scan
            data = await self.redis.get(key)
            if data:
                ep = EpisodicEvent(**json.loads(data))
                if ep.timestamp >= start_date:
                    if end_date is None or ep.timestamp <= end_date:
                        episodes.append(ep)

        episodes.sort(key=lambda e: e.timestamp, reverse=True)
        return episodes[:limit]

    async def search_episodes(self, query: str, limit: int = 5) -> List[EpisodicEvent]:
        """Search episodes by summary content."""
        # In production: use vector search (Qdrant/Chroma)
        # For now: simple keyword match
        if not self.redis:
            return []

        keys = await self.redis.keys("denis:episode:*")
        results = []

        for key in keys[:50]:
            data = await self.redis.get(key)
            if data:
                ep = EpisodicEvent(**json.loads(data))
                if (
                    query.lower() in ep.summary.lower()
                    or query.lower() in ep.topic.lower()
                ):
                    results.append(ep)

        return results[:limit]

    # M4: Narrative State
    async def get_narrative_state(self, user_id: str) -> NarrativeState:
        """Get narrative state for user."""
        if not self.redis:
            return NarrativeState()

        key = f"denis:narrative:{user_id}"
        data = await self.redis.get(key)

        if not data:
            return NarrativeState()

        d = json.loads(data)
        return NarrativeState(**d)

    async def update_narrative_state(self, user_id: str, state: NarrativeState):
        """Update narrative state."""
        if not self.redis:
            return

        state.last_update = datetime.now(timezone.utc).isoformat()
        state.last_update_ts = datetime.now(timezone.utc).isoformat()

        key = f"denis:narrative:{user_id}"
        await self.redis.set(key, json.dumps(state.to_dict()))

    async def add_follow_up(self, user_id: str, follow_up: Dict[str, Any]):
        """Add a follow-up to narrative state."""
        state = await self.get_narrative_state(user_id)
        state.pending_follow_ups.append(follow_up)
        await self.update_narrative_state(user_id, state)

    async def clear_resolved_follow_ups(self, user_id: str):
        """Clear resolved follow-ups."""
        state = await self.get_narrative_state(user_id)
        state.pending_follow_ups = [
            fu for fu in state.pending_follow_ups if not fu.get("resolved", False)
        ]
        await self.update_narrative_state(user_id, state)

    # Memory query router
    async def query(
        self,
        query_type: str,  # "recall", "follow_up", "person", "project"
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Route memory query to appropriate layer."""

        if query_type == "recall":
            # "do you remember..."
            time_hint = params.get("time_hint")  # "last Wednesday", "yesterday"
            topic = params.get("topic", "")

            if time_hint:
                # Try episodic by time
                episodes = await self.get_episodes_by_time_range(
                    start_date=params.get("start_date", "2020-01-01"), limit=3
                )
                return {"type": "episodic", "events": [e.to_dict() for e in episodes]}
            else:
                # Search by topic
                episodes = await self.search_episodes(topic, limit=3)
                return {"type": "episodic", "events": [e.to_dict() for e in episodes]}

        elif query_type == "follow_up":
            # Check pending follow-ups
            state = await self.get_narrative_state(params.get("user_id", "default"))
            return {"type": "follow_ups", "pending": state.pending_follow_ups}

        elif query_type == "person":
            # Look up person
            person = await self.get_person(params.get("person_id"))
            if person:
                return {"type": "person", "data": person.to_dict()}
            return {"type": "person", "data": None}

        return {"type": "unknown"}


# Global instance
_humanlike_memory: Optional[HumanlikeMemory] = None


def get_humanlike_memory(redis_client=None, neo4j_driver=None) -> HumanlikeMemory:
    """Get humanlike memory instance."""
    global _humanlike_memory
    if _humanlike_memory is None:
        _humanlike_memory = HumanlikeMemory(redis_client, neo4j_driver)
    return _humanlike_memory
