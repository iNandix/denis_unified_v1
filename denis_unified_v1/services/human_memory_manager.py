#!/usr/bin/env python3
"""
Human Memory Manager for Denis Persona.

Manages human-like memory: episodic events, people/pets, claims, artifacts.
Separate from IDE project memory.

Integrates with Neo4j for knowledge graph, Redis for narrative state, and event-bus.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from neo4j import GraphDatabase
import redis

logger = logging.getLogger(__name__)

# Reuse connections
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

@dataclass
class MemoryProposal:
    """Proposal for writing to human memory."""
    proposal_id: str = field(default_factory=lambda: str(uuid4()))
    type: str = ""  # episode, claim, person, pet
    payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    visibility: str = ""  # user:<id>, group:<id>
    user_id: str = ""
    group_id: str = ""
    accepted: bool = False
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class MemoryQuery:
    """Query for human memory."""
    query_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""
    group_id: str = ""
    query_text: str = ""
    time_hint: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)

class HumanMemoryManager:
    """Manages human knowledge graph and narrative state."""

    def __init__(self):
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.redis_client = redis.from_url(REDIS_URL)

        # Pending proposals
        self._proposals: Dict[str, MemoryProposal] = {}

        # Subscribe to events (assuming event_bus available)
        # self._subscribe_events()

    def _subscribe_events(self):
        """Subscribe to memory events."""
        # Assuming global event_bus
        from denis_unified_v1.cognitive_integration import get_cognitive_event_bus
        event_bus = get_cognitive_event_bus()
        event_bus.subscribe("memory.human.write_proposal", self._handle_write_proposal)
        event_bus.subscribe("memory.human.write_commit", self._handle_write_commit)
        event_bus.subscribe("memory.human.query", self._handle_query)
        event_bus.subscribe("memory.human.extract", self._handle_extract)

    def _handle_write_proposal(self, event):
        """Handle write proposal event."""
        data = event.data
        proposal = MemoryProposal(
            type=data.get("type"),
            payload=data.get("payload", {}),
            confidence=data.get("confidence", 0.0),
            visibility=data.get("visibility"),
            user_id=data.get("user_id"),
            group_id=data.get("group_id"),
        )
        self._proposals[proposal.proposal_id] = proposal
        logger.info(f"Proposal created: {proposal.proposal_id}")

    def _handle_write_commit(self, event):
        """Handle write commit event."""
        proposal_id = event.data.get("proposal_id")
        accepted = event.data.get("accepted", False)
        if proposal_id in self._proposals:
            proposal = self._proposals[proposal_id]
            proposal.accepted = accepted
            if accepted:
                self._execute_write(proposal)
            del self._proposals[proposal_id]

    def _handle_query(self, event):
        """Handle memory query event."""
        data = event.data
        query = MemoryQuery(
            user_id=data.get("user_id"),
            group_id=data.get("group_id"),
            query_text=data.get("query_text", ""),
            time_hint=data.get("time_hint"),
            entities=data.get("entities", []),
        )
        results = self._execute_query(query)
        # Emit result event
        from denis_unified_v1.cognitive_integration import get_cognitive_event_bus
        event_bus = get_cognitive_event_bus()
        event_bus.emit_neurolayer_event(
            "L3_EPISODIC", "memory.human.result", {"query_id": query.query_id, "results": results}
        )

    def _handle_extract(self, event):
        """Handle extract event (detect candidates)."""
        text = event.data.get("text", "")
        candidates = self._extract_candidates(text, event.data.get("user_id"), event.data.get("group_id"))
        for candidate in candidates:
            self._handle_write_proposal({"data": candidate})

    def _extract_candidates(self, text: str, user_id: str, group_id: str) -> List[Dict[str, Any]]:
        """Simple regex-based extraction (expand with Rasa/NLU later)."""
        candidates = []
        # Basic patterns
        if "miércoles" in text.lower() or "esta mañana" in text.lower():
            candidates.append({
                "type": "episode",
                "payload": {"title": "Detected episodic reference", "summary": text[:100]},
                "confidence": 0.8,
                "visibility": f"user:{user_id}",
                "user_id": user_id,
                "group_id": group_id,
            })
        # Add person/pet detection if needed
        return candidates

    def _execute_write(self, proposal: MemoryProposal):
        """Execute write to Neo4j."""
        with self.neo4j_driver.session() as session:
            if proposal.type == "episode":
                session.execute_write(self._create_episode, proposal.payload, proposal.visibility)
            elif proposal.type == "person":
                session.execute_write(self._create_person, proposal.payload)
            elif proposal.type == "pet":
                session.execute_write(self._create_pet, proposal.payload)
            elif proposal.type == "claim":
                session.execute_write(self._create_claim, proposal.payload, proposal.visibility)
            # Update Redis narrative
            self._update_narrative_state(proposal.user_id, proposal.group_id, proposal)

    def _create_episode(self, tx, payload: Dict[str, Any], visibility: str):
        query = """
        MERGE (e:Episode {episode_id: $episode_id})
        SET e.title = $title, e.summary = $summary, e.start_ts = $start_ts, e.status = $status,
            e.confidence = $confidence, e.visibility = $visibility, e.created_at = $created_at
        """
        tx.run(query, {
            "episode_id": str(uuid4()),
            "title": payload.get("title", ""),
            "summary": payload.get("summary", ""),
            "start_ts": payload.get("start_ts", datetime.now().isoformat()),
            "status": payload.get("status", "open"),
            "confidence": payload.get("confidence", 0.5),
            "visibility": visibility,
            "created_at": datetime.now().isoformat(),
        })

    def _create_person(self, tx, payload: Dict[str, Any]):
        query = """
        MERGE (p:Person {person_id: $person_id})
        SET p.name = $name, p.aliases = $aliases, p.created_at = $created_at
        """
        tx.run(query, {
            "person_id": str(uuid4()),
            "name": payload.get("name", ""),
            "aliases": payload.get("aliases", []),
            "created_at": datetime.now().isoformat(),
        })

    def _create_pet(self, tx, payload: Dict[str, Any]):
        query = """
        MERGE (pet:Pet {pet_id: $pet_id})
        SET pet.name = $name, pet.type = $type, pet.created_at = $created_at
        """
        tx.run(query, {
            "pet_id": str(uuid4()),
            "name": payload.get("name", ""),
            "type": payload.get("type", ""),
            "created_at": datetime.now().isoformat(),
        })

    def _create_claim(self, tx, payload: Dict[str, Any], visibility: str):
        query = """
        MERGE (c:Claim {claim_id: $claim_id})
        SET c.text = $text, c.ts = $ts, c.confidence = $confidence,
            c.source_type = $source_type, c.visibility = $visibility
        """
        tx.run(query, {
            "claim_id": str(uuid4()),
            "text": payload.get("text", ""),
            "ts": payload.get("ts", datetime.now().isoformat()),
            "confidence": payload.get("confidence", 0.5),
            "source_type": payload.get("source_type", "user"),
            "visibility": visibility,
        })

    def _update_narrative_state(self, user_id: str, group_id: str, proposal: MemoryProposal):
        """Update Redis narrative state."""
        key = f"narrative:{user_id}:{group_id}"
        state = json.loads(self.redis_client.get(key) or "{}")
        if proposal.type == "episode":
            state.setdefault("active_threads", []).append(proposal.payload.get("title", ""))
        # Add followup_due if needed
        self.redis_client.set(key, json.dumps(state), ex=7*24*3600)  # 7 days

    def _execute_query(self, query: MemoryQuery) -> Dict[str, Any]:
        """Execute query on Neo4j."""
        with self.neo4j_driver.session() as session:
            # Simple fulltext search
            results = session.run("""
            CALL db.index.fulltext.queryNodes("person_search", $query) YIELD node, score
            RETURN node, score LIMIT 5
            UNION
            CALL db.index.fulltext.queryNodes("episode_search", $query) YIELD node, score
            RETURN node, score LIMIT 5
            UNION
            CALL db.index.fulltext.queryNodes("claim_search", $query) YIELD node, score
            RETURN node, score LIMIT 5
            """, {"query": query.query_text})
            episodes = []
            claims = []
            people = []
            for record in results:
                node = record["node"]
                if node.labels == {"Episode"}:
                    episodes.append(dict(node))
                elif node.labels == {"Claim"}:
                    claims.append(dict(node))
                elif node.labels == {"Person"}:
                    people.append(dict(node))
            return {"episodes": episodes, "claims": claims, "people": people, "pets": []}  # Add pets if needed

    def get_narrative_state(self, user_id: str, group_id: str) -> Dict[str, Any]:
        """Get narrative state from Redis."""
        key = f"narrative:{user_id}:{group_id}"
        return json.loads(self.redis_client.get(key) or "{}")

    def close(self):
        """Close connections."""
        self.neo4j_driver.close()
        self.redis_client.close()

# Global instance
_human_memory_manager: Optional[HumanMemoryManager] = None

def get_human_memory_manager() -> HumanMemoryManager:
    """Get global HumanMemoryManager instance."""
    global _human_memory_manager
    if _human_memory_manager is None:
        _human_memory_manager = HumanMemoryManager()
    return _human_memory_manager

def reset_human_memory_manager():
    """Reset for testing."""
    global _human_memory_manager
    if _human_memory_manager:
        _human_memory_manager.close()
    _human_memory_manager = None
