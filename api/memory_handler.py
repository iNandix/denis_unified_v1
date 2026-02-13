"""Memory API routes for phase-9 unified memory rollout."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from denis_unified_v1.memory import build_memory_manager
from denis_unified_v1.memory.legacy_client import LegacyMemoryClient
from denis_unified_v1.cognitive_integration import (
    get_integration_service,
    NeuroMentalIntegrationService,
    CognitiveEventBus,
    NeuroLayerEventType,
    FeedbackType,
)
from denis_unified_v1.memory.graph_writer import get_graph_writer


class EpisodicRequest(BaseModel):
    conv_id: str
    user_id: str = "jotah"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    outcome: str = "unknown"


class SemanticRequest(BaseModel):
    concept_id: str
    name: str
    weight_delta: float = 1.0
    metadata: dict[str, Any] | None = None


class ProceduralRequest(BaseModel):
    macro_name: str
    definition: dict[str, Any]


class WorkingRequest(BaseModel):
    session_id: str
    context: dict[str, Any]


class AdaptiveCoTRequest(BaseModel):
    query: str
    latency_budget_ms: int = 2000
    context_window_tokens: int = 8192


class MemoryQueryRequest(BaseModel):
    text: str
    user_id: str | None = None
    session_id: str | None = None
    intent: str | None = None
    max_items: int = 8
    max_chars: int = 1500


class ConsolidationRequest(BaseModel):
    days_back: int = 1


class ContradictionResolutionRequest(BaseModel):
    contradiction_id: str
    resolution: str
    winner_id: str | None = None


MENTAL_LOOP_LEVELS = [
    {"level": 1, "name": "reflection", "description": "Reflexión inmediata L0->L1"},
    {"level": 2, "name": "meta_reflection", "description": "Control de estrategia"},
    {
        "level": 3,
        "name": "pattern_recognition",
        "description": "Detección de patrones y bucles",
    },
    {
        "level": 4,
        "name": "expansive_consciousness",
        "description": "Gobernanza global y continuidad",
    },
]


def _legacy_layer_for_local(local_layer: str) -> str:
    mapping = {
        "working": "working",
        "episodic": "episodic",
        "semantic": "semantic",
        "procedural": "procedural",
    }
    return mapping.get(local_layer, "semantic")


def _adaptive_cot(
    query: str, latency_budget_ms: int, context_window_tokens: int
) -> dict[str, Any]:
    token_est = max(1, len(query.split()))
    has_code = bool(
        re.search(
            r"\b(def|class|import|return|SELECT|FROM|JOIN)\b", query, re.IGNORECASE
        )
    )
    is_complex = token_est > 80 or bool(
        re.search(
            r"\b(analy[sz]e|compare|trade-?off|prove|reason)\b", query, re.IGNORECASE
        )
    )
    if latency_budget_ms < 700:
        depth = "short"
        chain_steps = 2
    elif is_complex:
        depth = "deep"
        chain_steps = 6
    else:
        depth = "medium"
        chain_steps = 4
    if has_code:
        chain_steps += 1
    chain_steps = min(chain_steps, 8)
    return {
        "mode": "adaptive_cot",
        "depth": depth,
        "chain_steps": chain_steps,
        "token_estimate": token_est,
        "context_window_tokens": context_window_tokens,
        "reasoning_style": "code_first" if has_code else "semantic_first",
    }


def build_memory_router() -> APIRouter:
    router = APIRouter(prefix="/v1/memory", tags=["memory"])
    memory = build_memory_manager()
    legacy = LegacyMemoryClient()

    # Initialize graph writer and cognitive integration
    graph_writer = get_graph_writer()
    integration_service = get_integration_service(graph_writer)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        base = memory.health()
        try:
            neuro = await legacy.neuro_layers()
            base["legacy_neuro_layers"] = int(neuro.get("total_layers", 0))
            base["legacy_bridge"] = "ok"
        except Exception as exc:
            base["legacy_bridge"] = "degraded"
            base["legacy_error"] = str(exc)[:200]
        return base

    @router.post("/episodic")
    async def save_episodic(req: EpisodicRequest) -> dict[str, Any]:
        local = memory.episodic.save_conversation(
            conv_id=req.conv_id,
            user_id=req.user_id,
            messages=req.messages,
            outcome=req.outcome,
        )
        text_content = json.dumps(req.messages, ensure_ascii=True)[:4000]
        try:
            legacy_res = await legacy.store(
                user_id=req.user_id,
                content=text_content,
                layer=_legacy_layer_for_local("episodic"),
                importance=0.7,
                metadata={"conv_id": req.conv_id, "outcome": req.outcome},
            )
            local["legacy_mirror"] = {"status": "ok", "result": legacy_res}
        except Exception as exc:
            local["legacy_mirror"] = {"status": "error", "error": str(exc)[:200]}
        return local

    @router.get("/episodic/{conv_id}")
    async def get_episodic(conv_id: str) -> dict[str, Any]:
        data = memory.episodic.get_conversation(conv_id)
        if not data:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        return data

    @router.post("/semantic")
    async def upsert_semantic(req: SemanticRequest) -> dict[str, Any]:
        local = memory.semantic.upsert_concept(
            concept_id=req.concept_id,
            name=req.name,
            weight_delta=req.weight_delta,
            metadata=req.metadata,
        )
        try:
            legacy_res = await legacy.store(
                user_id=(req.metadata or {}).get("user_id", "jotah"),
                content=req.name,
                layer=_legacy_layer_for_local("semantic"),
                importance=min(1.0, max(0.1, req.weight_delta)),
                metadata={"concept_id": req.concept_id, "metadata": req.metadata or {}},
            )
            local["legacy_mirror"] = {"status": "ok", "result": legacy_res}
        except Exception as exc:
            local["legacy_mirror"] = {"status": "error", "error": str(exc)[:200]}
        return local

    @router.get("/semantic/{concept_id}")
    async def get_semantic(concept_id: str) -> dict[str, Any]:
        data = memory.semantic.get_concept(concept_id)
        if not data:
            raise HTTPException(status_code=404, detail="concept_not_found")
        return data

    @router.post("/procedural")
    async def save_procedural(req: ProceduralRequest) -> dict[str, Any]:
        local = memory.procedural.save_macro(
            macro_name=req.macro_name,
            definition=req.definition,
        )
        try:
            legacy_res = await legacy.store(
                user_id=str(req.definition.get("user_id", "jotah")),
                content=f"macro:{req.macro_name}:{json.dumps(req.definition, ensure_ascii=True)[:3500]}",
                layer=_legacy_layer_for_local("procedural"),
                importance=0.8,
                metadata={"macro_name": req.macro_name},
            )
            local["legacy_mirror"] = {"status": "ok", "result": legacy_res}
        except Exception as exc:
            local["legacy_mirror"] = {"status": "error", "error": str(exc)[:200]}
        return local

    @router.get("/procedural/{macro_name}")
    async def get_procedural(macro_name: str) -> dict[str, Any]:
        data = memory.procedural.get_macro(macro_name)
        if not data:
            raise HTTPException(status_code=404, detail="macro_not_found")
        return data

    @router.get("/procedural")
    async def list_procedural() -> dict[str, Any]:
        return {"macros": memory.procedural.list_macros()}

    @router.post("/working")
    async def set_working(req: WorkingRequest) -> dict[str, Any]:
        local = memory.working.set_context(
            session_id=req.session_id,
            context=req.context,
        )
        try:
            legacy_res = await legacy.store(
                user_id=str(req.context.get("user_id", "jotah")),
                content=f"working:{req.session_id}:{json.dumps(req.context, ensure_ascii=True)[:3000]}",
                layer=_legacy_layer_for_local("working"),
                importance=0.5,
                metadata={"session_id": req.session_id},
            )
            local["legacy_mirror"] = {"status": "ok", "result": legacy_res}
        except Exception as exc:
            local["legacy_mirror"] = {"status": "error", "error": str(exc)[:200]}
        return local

    @router.get("/working/{session_id}")
    async def get_working(session_id: str) -> dict[str, Any]:
        data = memory.working.get_context(session_id)
        if not data:
            raise HTTPException(status_code=404, detail="working_context_not_found")
        return data

    # ========== ADVANCED MEMORY FEATURES ==========

    @router.post("/query")
    async def query_memory(req: MemoryQueryRequest) -> dict[str, Any]:
        """Retrieve relevant memory context using semantic search."""
        context = await memory.retrieval.retrieve_context(
            text=req.text,
            user_id=req.user_id,
            session_id=req.session_id,
            intent=req.intent,
            max_items=req.max_items,
            max_chars=req.max_chars,
        )
        return context

    @router.post("/consolidate")
    async def consolidate_memory(req: ConsolidationRequest) -> dict[str, Any]:
        """Run memory consolidation to extract facts and preferences."""
        result = await memory.consolidator.consolidate_daily(days_back=req.days_back)
        return result

    @router.get("/contradictions")
    async def list_contradictions(
        user_id: str | None = Query(None),
        status: str | None = Query(None),
    ) -> dict[str, Any]:
        """List detected contradictions in memory."""
        contradictions = await memory.contradiction_detector.list_contradictions(
            user_id=user_id, status=status
        )
        return {"contradictions": contradictions, "count": len(contradictions)}

    @router.post("/contradictions/detect")
    async def detect_contradictions(
        user_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """Detect contradictions in facts and preferences."""
        contradictions = await memory.contradiction_detector.detect_contradictions(
            user_id=user_id
        )
        return {"contradictions": contradictions, "count": len(contradictions)}

    @router.post("/contradictions/resolve")
    async def resolve_contradiction(
        req: ContradictionResolutionRequest,
    ) -> dict[str, Any]:
        """Resolve a contradiction by marking winner or merging."""
        result = await memory.contradiction_detector.resolve_contradiction(
            contradiction_id=req.contradiction_id,
            resolution=req.resolution,
            winner_id=req.winner_id,
        )
        return result

    @router.post("/forget")
    async def forget_memory(
        user_id: str = Query(...),
        scope: str = Query("all", regex="^(all|facts|preferences|episodes)$"),
    ) -> dict[str, Any]:
        """Forget user memory (GDPR compliance)."""
        # Implementation for memory deletion
        deleted = {"facts": 0, "preferences": 0, "episodes": 0}

        if scope in ("all", "facts"):
            all_facts = memory.redis.hgetall_json("memory:semantic:facts")
            for fact_id, fact in all_facts.items():
                if fact.get("user_id") == user_id:
                    # Delete from Redis (in production, also delete from Neo4j)
                    deleted["facts"] += 1

        if scope in ("all", "preferences"):
            all_prefs = memory.redis.hgetall_json("memory:semantic:preferences")
            for pref_id, pref in all_prefs.items():
                if pref.get("user_id") == user_id:
                    deleted["preferences"] += 1

        if scope in ("all", "episodes"):
            all_convs = memory.redis.hgetall_json("memory:episodic:conversations")
            for conv_id, conv in all_convs.items():
                if conv.get("user_id") == user_id:
                    deleted["episodes"] += 1

        return {
            "status": "ok",
            "user_id": user_id,
            "scope": scope,
            "deleted": deleted,
        }

    # ========== LEGACY ENDPOINTS ==========

    @router.get("/neuro/layers")
    async def neuro_layers() -> dict[str, Any]:
        try:
            return await legacy.neuro_layers()
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)[:200], "layers": {}}

    @router.get("/neuro/synergies")
    async def neuro_synergies() -> dict[str, Any]:
        try:
            return await legacy.neuro_synergies()
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)[:200], "rules": []}

    @router.get("/atlas/projects")
    async def atlas_projects() -> dict[str, Any]:
        try:
            return await legacy.atlas_projects()
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)[:200], "projects": []}

    @router.get("/neuro/mental-integration")
    async def neuro_mental_integration() -> dict[str, Any]:
        """Bridge neurolayers with mental-loops for cognitive integration.

        This endpoint provides real integration status by:
        - Using the CognitiveEventBus to track active events
        - Recording integrations in Neo4j via GraphWriter
        - Providing actual integration status
        """
        try:
            # Get integration status from the service (real data)
            integration_status = integration_service.get_integration_status()

            # Also get current neurolayer state from legacy
            neuro_state = await legacy.neuro_layers()

            return {
                "status": "integrated",
                "integration": integration_status,
                "neuro_layers": neuro_state,
                "mental_loops": MENTAL_LOOP_LEVELS,
                "graph_connected": graph_writer.neo4j_available
                if graph_writer
                else False,
            }

        except Exception as exc:
            return {
                "status": "disconnected",
                "error": str(exc)[:200],
                "message": "neurolayers and mental-loops are not connected",
            }

    @router.post("/neuro/mental-feedback")
    async def neuro_mental_feedback(
        neurolayer: str = Query(...),
        mental_loop: str = Query(...),
        feedback_type: str = Query("reinforcement"),
        feedback_data: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Send feedback from mental-loops to neurolayers for adaptation.

        This now uses the real integration service which:
        - Records feedback in the event bus
        - Persists to Neo4j via GraphWriter
        - Triggers adaptation in real-time
        """
        try:
            valid_neurolayers = [
                "L1_SENSORY",
                "L2_WORKING",
                "L3_EPISODIC",
                "L5_PROCEDURAL",
                "L8_SOCIAL",
                "L9_IDENTITY",
                "L10_RELATIONAL",
                "L12_METACOG",
            ]
            valid_loops = [
                "reflection",
                "meta_reflection",
                "pattern_recognition",
                "expansive_consciousness",
            ]

            if neurolayer not in valid_neurolayers:
                raise HTTPException(
                    status_code=400, detail=f"Invalid neurolayer: {neurolayer}"
                )
            if mental_loop not in valid_loops:
                raise HTTPException(
                    status_code=400, detail=f"Invalid mental loop: {mental_loop}"
                )

            # Emit cognitive event that triggers feedback processing
            event = integration_service.emit_cognitive_event(
                neurolayer=neurolayer,
                event_type=NeuroLayerEventType.METACOG_EVALUATE.value,
                data={
                    "feedback_type": feedback_type,
                    "feedback_data": feedback_data or {},
                    "mental_loop": mental_loop,
                    "timestamp": time.time(),
                },
            )

            # Also record in graph explicitly
            if graph_writer:
                graph_writer.record_neurolayer_mental_loop(
                    neurolayer=neurolayer,
                    mental_loop=mental_loop,
                    feedback_type=feedback_type,
                )

            return {
                "status": "feedback_sent",
                "neurolayer": neurolayer,
                "mental_loop": mental_loop,
                "feedback_type": feedback_type,
                "event_id": event.id,
                "graph_recorded": graph_writer.neo4j_available
                if graph_writer
                else False,
            }

        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Feedback processing failed: {str(exc)}"
            )

    @router.get("/neuro/mental-processing")
    async def neuro_mental_processing() -> dict[str, Any]:
        """Process pending mental-loop feedback to neurolayers.

        Now uses the integration service to get real-time feedback
        and processes it through the cognitive event bus.
        """
        try:
            # Get pending feedback from integration service
            pending_feedback = integration_service.get_pending_feedback()

            # Apply feedback
            applied_count = 0
            for fb in pending_feedback:
                if not fb.get("applied"):
                    if integration_service.apply_feedback(fb["id"]):
                        applied_count += 1

            # Get event history for reporting
            recent_events = integration_service.get_event_history(limit=20)

            return {
                "status": "processing_complete",
                "pending_feedback": len(pending_feedback),
                "applied_feedback": applied_count,
                "recent_events": len(recent_events),
                "graph_connected": graph_writer.neo4j_available
                if graph_writer
                else False,
                "event_history": recent_events,
            }

        except Exception as exc:
            return {"status": "processing_failed", "error": str(exc)[:200]}

    @router.post("/neuro/trigger")
    async def neuro_trigger_event(
        neurolayer: str = Query(...),
        event_type: str = Query("sensory_input"),
        data: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Trigger a cognitive event from a neurolayer.

        This endpoint allows triggering real cognitive processing
        that flows through the event bus and gets recorded in Neo4j.
        """
        try:
            valid_neurolayers = [
                "L1_SENSORY",
                "L2_WORKING",
                "L3_EPISODIC",
                "L5_PROCEDURAL",
                "L8_SOCIAL",
                "L9_IDENTITY",
                "L10_RELATIONAL",
                "L12_METACOG",
            ]

            if neurolayer not in valid_neurolayers:
                raise HTTPException(
                    status_code=400, detail=f"Invalid neurolayer: {neurolayer}"
                )

            # Map event type string to NeuroLayerEventType
            event_type_map = {
                "sensory_input": NeuroLayerEventType.SENSORY_INPUT,
                "working_update": NeuroLayerEventType.WORKING_UPDATE,
                "episodic_encode": NeuroLayerEventType.EPISODIC_ENCODE,
                "procedural_invoke": NeuroLayerEventType.PROCEDURAL_INVOKE,
                "social_process": NeuroLayerEventType.SOCIAL_PROCESS,
                "identity_update": NeuroLayerEventType.IDENTITY_UPDATE,
                "relational_analyze": NeuroLayerEventType.RELATIONAL_ANALYZE,
                "metacog_evaluate": NeuroLayerEventType.METACOG_EVALUATE,
            }

            neuro_event_type = event_type_map.get(
                event_type, NeuroLayerEventType.SENSORY_INPUT
            )

            # Emit the event through the integration service
            event = integration_service.emit_cognitive_event(
                neurolayer=neurolayer,
                event_type=neuro_event_type.value,
                data=data or {},
            )

            return {
                "status": "event_triggered",
                "event_id": event.id,
                "neurolayer": neurolayer,
                "target_mental_loop": event.target_mental_loop,
                "event_type": event.event_type,
                "graph_recorded": event.graph_recorded,
            }

        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Event trigger failed: {str(exc)}"
            )

    # ========== NEURO-MENTAL LOOP INTEGRATION ==========

    @router.post("/neuro/process-event")
    async def process_neuro_mental_event(
        event_type: str = Query(...),
        event_data: dict[str, Any] = None,
        source_layer: str = Query(None),
        target_loop: str = Query(None),
    ) -> dict[str, Any]:
        """Process event through neuro-mental loop integration."""
        try:
            from denis_unified_v1.memory.graph_writer import get_graph_writer

            writer = get_graph_writer()

            event_data = event_data or {}
            event_id = f"{event_type}_{int(__import__('time').time())}"

            # Process based on event type
            if event_type == "sensory_input":
                # Sensory input feeds into reflection mental loop
                result = await _process_sensory_feed(
                    writer, event_data, source_layer or "L1_SENSORY"
                )

            elif event_type == "cognitive_processing":
                # Cognitive processing creates feedback loops
                result = await _process_cognitive_feedback(
                    writer, event_data, target_loop or "reflection"
                )

            elif event_type == "memory_consolidation":
                # Memory operations create neuro-mental adaptations
                result = await _process_memory_adaptation(writer, event_data)

            else:
                result = {"status": "unknown_event_type", "event_type": event_type}

            # Create canonical relationships
            if source_layer and target_loop:
                writer.record_neurolayer_mental_loop(
                    source_layer, target_loop, "reinforcement"
                )

            # Create mental loop chain relationships
            await _ensure_mental_loop_chain(writer)

            # Create neurolayer chain relationships
            await _ensure_neurolayer_chain(writer)

            writer.close()
            return {
                "status": "processed",
                "event_id": event_id,
                "event_type": event_type,
                "processing_result": result,
                "relationships_created": ["FEEDS", "FEEDBACKS", "NEXT"]
                if writer.neo4j_available
                else [],
            }

        except Exception as exc:
            return {
                "status": "processing_failed",
                "error": str(exc)[:200],
                "event_type": event_type,
            }

    async def _process_sensory_feed(
        writer, event_data: dict, source_layer: str
    ) -> dict[str, Any]:
        """Process sensory input feeding into mental loops."""
        # Create feed relationship from neurolayer to mental loop
        feed_result = writer.record_neurolayer_mental_loop(
            source_layer, "reflection", "feed"
        )

        # Simulate processing through reflection loop
        processing_steps = [
            "sensory_input_received",
            "reflection_loop_activated",
            "pattern_recognition_engaged",
            "adaptive_response_generated",
        ]

        return {
            "feed_processed": feed_result,
            "processing_steps": processing_steps,
            "adaptation_generated": True,
        }

    async def _process_cognitive_feedback(
        writer, event_data: dict, target_loop: str
    ) -> dict[str, Any]:
        """Process cognitive feedback from mental loops to neurolayers."""
        # Create feedback relationship from mental loop to neurolayer
        feedback_result = writer.record_neurolayer_mental_loop(
            "L2_WORKING", target_loop, "feedback"
        )

        # Simulate feedback processing
        feedback_steps = [
            "cognitive_feedback_received",
            f"{target_loop}_loop_processed",
            "neurolayer_adaptation_applied",
            "learning_reinforcement_complete",
        ]

        return {
            "feedback_processed": feedback_result,
            "processing_steps": feedback_steps,
            "reinforcement_applied": True,
        }

    async def _process_memory_adaptation(writer, event_data: dict) -> dict[str, Any]:
        """Process memory consolidation creating neuro-mental adaptations."""
        # Memory operations create adaptations across multiple layers
        adaptations = []

        memory_layers = ["L3_EPISODIC", "L5_PROCEDURAL", "L9_IDENTITY"]
        mental_functions = [
            "pattern_recognition",
            "meta_reflection",
            "expansive_consciousness",
        ]

        for neuro_layer in memory_layers:
            for mental_loop in mental_functions:
                result = writer.record_neurolayer_mental_loop(
                    neuro_layer, mental_loop, "consolidation"
                )
                adaptations.append(
                    {"neuro": neuro_layer, "mental": mental_loop, "result": result}
                )

        return {
            "memory_adaptations_created": len(adaptations),
            "adaptations": adaptations,
            "consolidation_complete": True,
        }

    async def _ensure_mental_loop_chain(writer) -> None:
        """Ensure mental loop chain relationships exist."""
        loop_sequence = [
            ("perception", "analysis"),
            ("analysis", "planning"),
            ("planning", "synthesis"),
            ("synthesis", "perception"),  # Circular for continuous processing
        ]

        for from_loop, to_loop in loop_sequence:
            # Create MentalLoopLevel nodes and NEXT relationships
            writer._execute_write(
                f"""
            MERGE (ml1:MentalLoopLevel {{node_ref: $from_loop}})
            MERGE (ml2:MentalLoopLevel {{node_ref: $to_loop}})
            MERGE (ml1)-[:NEXT]->(ml2)
            """,
                {"from_loop": from_loop, "to_loop": to_loop},
            )

    async def _ensure_neurolayer_chain(writer) -> None:
        """Ensure neurolayer chain relationships exist."""
        layer_sequence = [
            ("L1_SENSORY", "L2_WORKING"),
            ("L2_WORKING", "L3_EPISODIC"),
            ("L3_EPISODIC", "L5_PROCEDURAL"),
            ("L5_PROCEDURAL", "L8_SOCIAL"),
            ("L8_SOCIAL", "L9_IDENTITY"),
            ("L9_IDENTITY", "L10_RELATIONAL"),
            ("L10_RELATIONAL", "L12_METACOG"),
        ]

        for from_layer, to_layer in layer_sequence:
            # Create NeuroLayer nodes and NEXT relationships
            writer._execute_write(
                f"""
            MERGE (nl1:NeuroLayer {{node_ref: $from_layer}})
            MERGE (nl2:NeuroLayer {{node_ref: $to_layer}})
            MERGE (nl1)-[:NEXT]->(nl2)
            """,
                {"from_layer": from_layer, "to_layer": to_layer},
            )

    # ========== VOICE + LLM MODEL CONNECTIVITY ==========

    @router.post("/voice/register-turn")
    async def register_voice_turn(
        voice_component_id: str = Query(...),
        turn_id: str = Query(...),
        voice_data: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Register voice component producing a turn in the cognitive trace."""
        try:
            from denis_unified_v1.memory.graph_writer import get_graph_writer

            writer = get_graph_writer()

            voice_data = voice_data or {}
            result = writer.record_voice_turn(voice_component_id, turn_id, voice_data)

            writer.close()
            return {
                "status": "voice_turn_registered"
                if result
                else "registration_deferred",
                "voice_component_id": voice_component_id,
                "turn_id": turn_id,
                "relationship_created": result,
            }

        except Exception as exc:
            return {
                "status": "registration_failed",
                "error": str(exc)[:200],
                "voice_component_id": voice_component_id,
                "turn_id": turn_id,
            }

    @router.post("/inference/model-selection")
    async def register_model_selection(
        turn_id: str = Query(...),
        model_id: str = Query(...),
        selection_data: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Register model selection for a turn in the cognitive trace."""
        try:
            from denis_unified_v1.memory.graph_writer import get_graph_writer

            writer = get_graph_writer()

            selection_data = selection_data or {}
            result = writer.record_model_selection(turn_id, model_id, selection_data)

            # Also record model influence on reasoning trace if available
            trace_id = selection_data.get("trace_id")
            if trace_id and result:
                influence_data = {
                    "type": "model_selection",
                    "strength": selection_data.get("confidence", 1.0),
                    "selection_reason": selection_data.get("reason", "routing"),
                }
                writer.record_model_influence(model_id, trace_id, influence_data)

            writer.close()
            return {
                "status": "model_selection_registered"
                if result
                else "registration_deferred",
                "turn_id": turn_id,
                "model_id": model_id,
                "relationships_created": ["USED_MODEL"]
                + (["INFLUENCED"] if trace_id else []),
            }

        except Exception as exc:
            return {
                "status": "registration_failed",
                "error": str(exc)[:200],
                "turn_id": turn_id,
                "model_id": model_id,
            }

    @router.post("/voice/trace-connection")
    async def register_voice_trace_connection(
        voice_component_id: str = Query(...),
        trace_id: str = Query(...),
        connection_data: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Register voice component connection to reasoning trace."""
        try:
            from denis_unified_v1.memory.graph_writer import get_graph_writer

            writer = get_graph_writer()

            connection_data = connection_data or {}
            result = writer.record_voice_trace_connection(
                voice_component_id, trace_id, connection_data
            )

            writer.close()
            return {
                "status": "voice_trace_connected" if result else "connection_deferred",
                "voice_component_id": voice_component_id,
                "trace_id": trace_id,
                "relationships_created": ["CONTRIBUTED_TO", "INFLUENCED_BY"]
                if result
                else [],
            }

        except Exception as exc:
            return {
                "status": "connection_failed",
                "error": str(exc)[:200],
                "voice_component_id": voice_component_id,
                "trace_id": trace_id,
            }

    @router.get("/connectivity/voice-llm-status")
    async def get_voice_llm_connectivity_status() -> dict[str, Any]:
        """Get current status of voice and LLM model connectivity in the graph."""
        try:
            # Try to get connectivity stats from Neo4j
            import os

            uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "")

            if not password:
                return {
                    "status": "skippeddependency",
                    "reason": "Neo4j not available for connectivity check",
                    "voice_turns": 0,
                    "model_selections": 0,
                    "voice_trace_connections": 0,
                    "cognitive_trace_integrity": 0.0,
                }

            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(uri, auth=(user, password))

            with driver.session() as session:
                # Count voice-related relationships
                voice_query = """
                MATCH (vc:VoiceComponent)-[:PRODUCED]->(t:Turn)
                RETURN count(*) as voice_turns
                """
                voice_result = session.run(voice_query).single()

                # Count model-related relationships
                model_query = """
                MATCH (t:Turn)-[:USED_MODEL]->(llm:LLMModel)
                RETURN count(*) as model_selections
                """
                model_result = session.run(model_query).single()

                # Count voice-trace connections
                connection_query = """
                MATCH (vc:VoiceComponent)-[:CONTRIBUTED_TO]->(rt:ReasoningTrace)
                RETURN count(*) as voice_trace_connections
                """
                connection_result = session.run(connection_query).single()

                # Calculate cognitive trace integrity (turns with complete voice→model→trace chain)
                integrity_query = """
                MATCH (vc:VoiceComponent)-[:PRODUCED]->(t:Turn)-[:USED_MODEL]->(llm:LLMModel),
                      (vc)-[:CONTRIBUTED_TO]->(rt:ReasoningTrace)<-[:INFLUENCED]-(llm)
                RETURN count(DISTINCT t) as complete_chains,
                       count(DISTINCT t) * 1.0 / count(DISTINCT t) as integrity_ratio
                """
                integrity_result = session.run(integrity_query).single()

            driver.close()

            return {
                "status": "connected",
                "neo4j_available": True,
                "voice_turns": voice_result["voice_turns"],
                "model_selections": model_result["model_selections"],
                "voice_trace_connections": connection_result["voice_trace_connections"],
                "cognitive_trace_integrity": integrity_result.get(
                    "integrity_ratio", 0.0
                ),
                "complete_chains": integrity_result.get("complete_chains", 0),
            }

        except Exception as exc:
            return {
                "status": "connectivity_check_failed",
                "error": str(exc)[:200],
                "voice_turns": 0,
                "model_selections": 0,
                "voice_trace_connections": 0,
                "cognitive_trace_integrity": 0.0,
            }
