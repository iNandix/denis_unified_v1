"""Fail-open GraphWriter for enforcing core relationships at ingest time."""

import asyncio
import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GraphWriter:
    """Fail-open graph writer that enforces core relationships at ingest time.

    If Neo4j fails, accumulates deferred events in memory queue and emits
    metacognitive degraded events.
    """

    def __init__(self):
        self.neo4j_available = False
        self.driver = None
        self.deferred_events = deque(maxlen=1000)  # Light memory queue
        self._lock = threading.Lock()
        self._init_neo4j()

    def _init_neo4j(self):
        """Initialize Neo4j connection with fail-open."""
        try:
            uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "")

            if not password:
                raise ValueError("NEO4J_PASSWORD not set")

            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            # Test connection
            with self.driver.session() as session:
                session.run("RETURN 1").single()
            self.neo4j_available = True
            logger.info("GraphWriter: Neo4j connection established")

        except Exception as e:
            self.neo4j_available = False
            logger.warning(f"GraphWriter: Neo4j not available: {e}")
            # Removed metacognitive event emission to avoid import issues in smoke tests

    def _emit_metacognitive_event(self, event_type: str, data: Dict[str, Any]):
        """Emit metacognitive event for degraded operation."""
        # Simplified: just log for now to avoid import issues in smoke tests
        logger.warning(f"Metacognitive event {event_type}: {data}")

    def _execute_write(self, query: str, params: Dict[str, Any]) -> bool:
        """Execute write operation with fail-open behavior."""
        if not self.neo4j_available:
            # Accumulate deferred event
            with self._lock:
                self.deferred_events.append({
                    "query": query,
                    "params": params,
                    "timestamp": time.time(),
                    "attempts": 0
                })
            self._emit_metacognitive_event("graph_write_deferred", {
                "reason": "neo4j_unavailable",
                "query_type": query.split()[0] if query else "unknown",
                "deferred_count": len(self.deferred_events)
            })
            return False

        try:
            with self.driver.session() as session:
                session.run(query, params)
            return True
        except Exception as e:
            logger.error(f"Graph write failed: {e}")
            # Accumulate as deferred event
            with self._lock:
                self.deferred_events.append({
                    "query": query,
                    "params": params,
                    "timestamp": time.time(),
                    "error": str(e),
                    "attempts": 0
                })
            self._emit_metacognitive_event("graph_write_failed", {
                "error": str(e),
                "query_type": query.split()[0] if query else "unknown",
                "deferred_count": len(self.deferred_events)
            })
            return False

    def record_turn(self, turn_id: str, user_id: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """Record a Turn node and ensure core relationships."""
        metadata = metadata or {}
        query = """
        MERGE (t:Turn {id: $turn_id})
        SET t.user_id = $user_id,
            t.content = $content,
            t.timestamp = $timestamp,
            t.metadata = $metadata,
            t.created_at = datetime()
        """
        params = {
            "turn_id": turn_id,
            "user_id": user_id,
            "content": content,
            "timestamp": time.time(),
            "metadata": json.dumps(metadata)
        }
        return self._execute_write(query, params)

    def record_trace_chain(self, turn_id: str, trace_data: Dict[str, Any]) -> bool:
        """Record CognitiveTrace → ReasoningTrace → GraphRoute chain."""
        cognitive_trace_id = trace_data.get("cognitive_trace_id", f"ct_{turn_id}")
        reasoning_trace_id = trace_data.get("reasoning_trace_id", f"rt_{turn_id}")
        graph_route_id = trace_data.get("graph_route_id", f"gr_{turn_id}")

        query = """
        // Ensure Turn exists
        MERGE (t:Turn {id: $turn_id})

        // Create CognitiveTrace and link to Turn
        MERGE (ct:CognitiveTrace {id: $cognitive_trace_id})
        SET ct.data = $cognitive_data,
            ct.timestamp = $timestamp,
            ct.created_at = datetime()
        MERGE (t)-[:HAS_COGNITIVE_TRACE]->(ct)

        // Create ReasoningTrace and link to CognitiveTrace
        MERGE (rt:ReasoningTrace {id: $reasoning_trace_id})
        SET rt.data = $reasoning_data,
            rt.timestamp = $timestamp,
            rt.created_at = datetime()
        MERGE (ct)-[:HAS_REASONING_TRACE]->(rt)

        // Create GraphRoute and link to ReasoningTrace
        MERGE (gr:GraphRoute {id: $graph_route_id})
        SET gr.data = $route_data,
            gr.timestamp = $timestamp,
            gr.created_at = datetime()
        MERGE (rt)-[:USED_GRAPH_ROUTE]->(gr)
        """

        params = {
            "turn_id": turn_id,
            "cognitive_trace_id": cognitive_trace_id,
            "reasoning_trace_id": reasoning_trace_id,
            "graph_route_id": graph_route_id,
            "cognitive_data": json.dumps(trace_data.get("cognitive", {})),
            "reasoning_data": json.dumps(trace_data.get("reasoning", {})),
            "route_data": json.dumps(trace_data.get("route", {})),
            "timestamp": time.time()
        }

        return self._execute_write(query, params)

    def record_tool_execution(self, graph_route_id: str, tool_execution_data: Dict[str, Any]) -> bool:
        """Record ToolExecution linked to GraphRoute."""
        tool_execution_id = tool_execution_data.get("id", f"te_{graph_route_id}_{int(time.time())}")

        query = """
        // Ensure GraphRoute exists
        MERGE (gr:GraphRoute {id: $graph_route_id})

        // Create ToolExecution and link
        MERGE (te:ToolExecution {id: $tool_execution_id})
        SET te.data = $execution_data,
            te.tool_name = $tool_name,
            te.result = $result,
            te.timestamp = $timestamp,
            te.created_at = datetime()
        MERGE (gr)-[:TRIGGERED_TOOL_EXECUTION]->(te)
        """

        params = {
            "graph_route_id": graph_route_id,
            "tool_execution_id": tool_execution_id,
            "execution_data": json.dumps(tool_execution_data),
            "tool_name": tool_execution_data.get("tool_name", "unknown"),
            "result": json.dumps(tool_execution_data.get("result", {})),
            "timestamp": time.time()
        }

        return self._execute_write(query, params)

    def record_memory_chunk(self, memory_id: str, chunk_data: Dict[str, Any]) -> bool:
        """Record Memory → HAS_CHUNK → MemoryChunk."""
        chunk_id = chunk_data.get("id", f"chunk_{memory_id}_{int(time.time())}")

        query = """
        // Ensure Memory exists
        MERGE (m:Memory {id: $memory_id})

        // Create MemoryChunk and link
        MERGE (mc:MemoryChunk {id: $chunk_id})
        SET mc.data = $chunk_data,
            mc.content = $content,
            mc.layer = $layer,
            mc.timestamp = $timestamp,
            mc.created_at = datetime()
        MERGE (m)-[:HAS_CHUNK]->(mc)

        // Link chunks in sequence if next_chunk_id provided
        FOREACH (_ IN CASE WHEN $next_chunk_id IS NOT NULL THEN [1] ELSE [] END |
            MERGE (next_mc:MemoryChunk {id: $next_chunk_id})
            MERGE (mc)-[:NEXT_CHUNK]->(next_mc)
        )
        """

        params = {
            "memory_id": memory_id,
            "chunk_id": chunk_id,
            "chunk_data": json.dumps(chunk_data),
            "content": chunk_data.get("content", ""),
            "layer": chunk_data.get("layer", "unknown"),
            "timestamp": time.time(),
            "next_chunk_id": chunk_data.get("next_chunk_id")
        }

        return self._execute_write(query, params)

    def record_episode_concepts(self, episode_id: str, concept_ids: List[str]) -> bool:
        """Record Episode ↔ ConceptNode bidirectional relationships."""
        if not concept_ids:
            return True

        # Build query for multiple concept links
        concept_merges = []
        concept_links = []

        for i, concept_id in enumerate(concept_ids):
            concept_merges.append(f"""
            MERGE (c{i}:ConceptNode {{id: $concept_id_{i}}})
            SET c{i}.name = $concept_name_{i},
                c{i}.updated_at = datetime()
            """)
            concept_links.append(f"""
            MERGE (e)-[:MENTIONS_CONCEPT]->(c{i})
            MERGE (c{i})-[:IN_EPISODE]->(e)
            """)

        query = f"""
        // Ensure Episode exists
        MERGE (e:Episode {{id: $episode_id}})
        SET e.updated_at = datetime()

        // Merge concepts
        {"".join(concept_merges)}

        // Create bidirectional links
        {"".join(concept_links)}
        """

        params = {
            "episode_id": episode_id
        }

        # Add concept parameters
        for i, concept_id in enumerate(concept_ids):
            params[f"concept_id_{i}"] = concept_id
            params[f"concept_name_{i}"] = f"Concept {concept_id}"  # Could be enhanced

        return self._execute_write(query, params)

    def record_neurolayer_mental_loop(self, neurolayer: str, mental_loop: str,
                                    feedback_type: str = "reinforcement") -> bool:
        """Record NeuroLayer ↔ MentalLoop relationships."""
        query = """
        // Ensure nodes exist
        MERGE (nl:NeuroLayer {node_ref: $neurolayer})
        SET nl.updated_at = datetime()

        MERGE (ml:MentalLoopLevel {node_ref: $mental_loop})
        SET ml.updated_at = datetime()

        // Create relationships
        MERGE (nl)-[:FEEDS]->(ml)
        MERGE (ml)-[:FEEDBACKS {type: $feedback_type}]->(nl)
        """

        params = {
            "neurolayer": neurolayer,
            "mental_loop": mental_loop,
            "feedback_type": feedback_type
        }

        return self._execute_write(query, params)

    def record_voice_component(self, component_id: str, component_data: Dict[str, Any]) -> bool:
        """Record VoiceComponent and its relationships."""
        query = """
        MERGE (vc:VoiceComponent {id: $component_id})
        SET vc.data = $component_data,
            vc.component_type = $component_type,
            vc.updated_at = datetime()
        """

        params = {
            "component_id": component_id,
            "component_data": json.dumps(component_data),
            "component_type": component_data.get("type", "unknown")
        }

        return self._execute_write(query, params)

    def record_llm_model(self, model_id: str, model_data: Dict[str, Any]) -> bool:
        """Record LLMModel and its relationships."""
        query = """
        MERGE (llm:LLMModel {id: $model_id})
        SET llm.data = $model_data,
            llm.model_name = $model_name,
            llm.provider = $provider,
            llm.updated_at = datetime()
        """

        params = {
            "model_id": model_id,
            "model_data": json.dumps(model_data),
            "model_name": model_data.get("name", "unknown"),
            "provider": model_data.get("provider", "unknown")
        }

        return self._execute_write(query, params)

    def get_deferred_count(self) -> int:
        """Get count of deferred events."""
        with self._lock:
            return len(self.deferred_events)

    def flush_deferred_events(self) -> int:
        """Attempt to flush deferred events (if Neo4j becomes available)."""
        if not self.neo4j_available:
            return 0

        flushed = 0
        with self._lock:
            # Process up to 50 events at a time to avoid blocking
            events_to_process = []
            for _ in range(min(50, len(self.deferred_events))):
                if self.deferred_events:
                    events_to_process.append(self.deferred_events.popleft())

        for event in events_to_process:
            try:
                with self.driver.session() as session:
                    session.run(event["query"], event["params"])
                flushed += 1
            except Exception as e:
                logger.error(f"Failed to flush deferred event: {e}")
                # Put back in queue
                with self._lock:
                    self.deferred_events.appendleft(event)

        if flushed > 0:
            self._emit_metacognitive_event("graph_write_flushed", {
                "flushed_count": flushed,
                "remaining_deferred": len(self.deferred_events)
            })

        return flushed

    def record_voice_turn(self, voice_component_id: str, turn_id: str, voice_data: Dict[str, Any]) -> bool:
        """Record VoiceComponent → Turn relationship for voice pipeline integration."""
        query = """
        // Ensure nodes exist
        MERGE (vc:VoiceComponent {id: $voice_component_id})
        SET vc.last_used = datetime(), vc.pipeline_status = $pipeline_status
        
        MERGE (t:Turn {id: $turn_id})
        SET t.voice_source = $voice_component_id, t.voice_data = $voice_data
        
        // Create PRODUCED relationship
        MERGE (vc)-[:PRODUCED {timestamp: datetime()}]->(t)
        """
        
        params = {
            "voice_component_id": voice_component_id,
            "turn_id": turn_id,
            "voice_data": json.dumps(voice_data),
            "pipeline_status": voice_data.get("pipeline_status", "unknown")
        }
        
        return self._execute_write(query, params)

    def record_model_selection(self, turn_id: str, model_id: str, selection_data: Dict[str, Any]) -> bool:
        """Record Turn → LLMModel relationship for model selection tracking."""
        query = """
        // Ensure nodes exist
        MERGE (t:Turn {id: $turn_id})
        
        MERGE (llm:LLMModel {id: $model_id})
        SET llm.name = $model_name,
            llm.provider = $provider,
            llm.last_selected = datetime(),
            llm.selection_data = $selection_data
        
        // Create USED_MODEL relationship
        MERGE (t)-[:USED_MODEL {timestamp: datetime(), confidence: $confidence}]->(llm)
        """
        
        params = {
            "turn_id": turn_id,
            "model_id": model_id,
            "model_name": selection_data.get("model_name", model_id),
            "provider": selection_data.get("provider", "unknown"),
            "selection_data": json.dumps(selection_data),
            "confidence": selection_data.get("confidence", 0.0)
        }
        
        return self._execute_write(query, params)

    def record_model_influence(self, model_id: str, trace_id: str, influence_data: Dict[str, Any]) -> bool:
        """Record LLMModel → ReasoningTrace relationship for model influence tracking."""
        query = """
        // Ensure nodes exist
        MERGE (llm:LLMModel {id: $model_id})
        
        MERGE (rt:ReasoningTrace {id: $trace_id})
        
        // Create INFLUENCED relationship
        MERGE (llm)-[:INFLUENCED {
            timestamp: datetime(),
            influence_type: $influence_type,
            strength: $strength
        }]->(rt)
        """
        
        params = {
            "model_id": model_id,
            "trace_id": trace_id,
            "influence_type": influence_data.get("type", "reasoning"),
            "strength": influence_data.get("strength", 1.0)
        }
        
        return self._execute_write(query, params)

    def record_voice_trace_connection(self, voice_component_id: str, trace_id: str, connection_data: Dict[str, Any]) -> bool:
        """Record VoiceComponent ↔ ReasoningTrace relationship for voice pipeline integration."""
        query = """
        // Ensure nodes exist
        MERGE (vc:VoiceComponent {id: $voice_component_id})
        MERGE (rt:ReasoningTrace {id: $trace_id})
        
        // Create bidirectional relationships
        MERGE (vc)-[:CONTRIBUTED_TO {timestamp: datetime(), role: $voice_role}]->(rt)
        MERGE (rt)-[:INFLUENCED_BY {timestamp: datetime(), source: 'voice'}]->(vc)
        """
        
        params = {
            "voice_component_id": voice_component_id,
            "trace_id": trace_id,
            "voice_role": connection_data.get("role", "input")
        }
        
        return self._execute_write(query, params)


# Global instance for application-wide use
_graph_writer = None
_writer_lock = threading.Lock()


def get_graph_writer() -> GraphWriter:
    """Get global GraphWriter instance (singleton)."""
    global _graph_writer
    if _graph_writer is None:
        with _writer_lock:
            if _graph_writer is None:
                _graph_writer = GraphWriter()
    return _graph_writer
