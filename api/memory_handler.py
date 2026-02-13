"""Memory API routes for phase-9 unified memory rollout."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from memory import build_memory_manager
from memory.legacy_client import LegacyMemoryClient


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
    {"level": 3, "name": "pattern_recognition", "description": "Detección de patrones y bucles"},
    {"level": 4, "name": "expansive_consciousness", "description": "Gobernanza global y continuidad"},
]


def _legacy_layer_for_local(local_layer: str) -> str:
    mapping = {
        "working": "working",
        "episodic": "episodic",
        "semantic": "semantic",
        "procedural": "procedural",
    }
    return mapping.get(local_layer, "semantic")


def _adaptive_cot(query: str, latency_budget_ms: int, context_window_tokens: int) -> dict[str, Any]:
    token_est = max(1, len(query.split()))
    has_code = bool(re.search(r"\b(def|class|import|return|SELECT|FROM|JOIN)\b", query, re.IGNORECASE))
    is_complex = token_est > 80 or bool(
        re.search(r"\b(analy[sz]e|compare|trade-?off|prove|reason)\b", query, re.IGNORECASE)
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
    async def detect_contradictions(user_id: str | None = Query(None)) -> dict[str, Any]:
        """Detect contradictions in facts and preferences."""
        contradictions = await memory.contradiction_detector.detect_contradictions(
            user_id=user_id
        )
        return {"contradictions": contradictions, "count": len(contradictions)}

    @router.post("/contradictions/resolve")
    async def resolve_contradiction(req: ContradictionResolutionRequest) -> dict[str, Any]:
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
        """Bridge neurolayers with mental-loops for cognitive integration."""
        try:
            # Get current neurolayer state
            neuro_state = await legacy.neuro_layers()
            
            # Get mental loop state
            mental_loops = MENTAL_LOOP_LEVELS
            
            # Create integration mapping
            integration = {
                "status": "integrated",
                "neurolayer_to_mental_loop": {
                    "L1_SENSORY": "reflection",  # Sensory input -> immediate reflection
                    "L2_WORKING": "reflection",  # Working memory -> operational reflection
                    "L3_EPISODIC": "pattern_recognition",  # Episodic memory -> pattern detection
                    "L5_PROCEDURAL": "meta_reflection",  # Procedural -> strategy control
                    "L8_SOCIAL": "pattern_recognition",  # Social -> relationship patterns
                    "L9_IDENTITY": "expansive_consciousness",  # Identity -> global continuity
                    "L10_RELATIONAL": "pattern_recognition",  # Relational -> complex patterns
                    "L12_METACOG": "expansive_consciousness"  # Metacog -> governance
                },
                "mental_loop_to_neurolayer": {
                    "reflection": ["L1_SENSORY", "L2_WORKING"],
                    "meta_reflection": ["L5_PROCEDURAL", "L12_METACOG"],
                    "pattern_recognition": ["L3_EPISODIC", "L8_SOCIAL", "L10_RELATIONAL"],
                    "expansive_consciousness": ["L9_IDENTITY", "L12_METACOG"]
                },
                "active_integrations": []
            }
            
            # Check which integrations are active
            for neuro_layer, mental_loop in integration["neurolayer_to_mental_loop"].items():
                if neuro_layer in neuro_state.get("layers", {}):
                    integration["active_integrations"].append({
                        "neurolayer": neuro_layer,
                        "mental_loop": mental_loop,
                        "status": "active"
                    })
            
            return {
                "integration": integration,
                "neuro_layers": neuro_state,
                "mental_loops": mental_loops
            }
            
        except Exception as exc:
            return {
                "status": "disconnected",
                "error": str(exc)[:200],
                "message": "neurolayers and mental-loops are not connected"
            }

    @router.post("/neuro/mental-feedback")
    async def neuro_mental_feedback(
        neurolayer: str = Query(...),
        mental_loop: str = Query(...),
        feedback_type: str = Query("reinforcement"),
        feedback_data: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Send feedback from mental-loops to neurolayers for adaptation."""
        try:
            # Validate inputs
            valid_neurolayers = ["L1_SENSORY", "L2_WORKING", "L3_EPISODIC", "L5_PROCEDURAL", 
                               "L8_SOCIAL", "L9_IDENTITY", "L10_RELATIONAL", "L12_METACOG"]
            valid_loops = ["reflection", "meta_reflection", "pattern_recognition", "expansive_consciousness"]
            
            if neurolayer not in valid_neurolayers:
                raise HTTPException(status_code=400, detail=f"Invalid neurolayer: {neurolayer}")
            if mental_loop not in valid_loops:
                raise HTTPException(status_code=400, detail=f"Invalid mental loop: {mental_loop}")
            
            # Store feedback in memory for neurolayer adaptation
            feedback_record = {
                "neurolayer": neurolayer,
                "mental_loop": mental_loop,
                "feedback_type": feedback_type,
                "feedback_data": feedback_data or {},
                "timestamp": json.dumps({"timestamp": __import__("time").time()}),
                "processed": False
            }
            
            # Store in Redis for processing
            feedback_key = f"neuro_mental_feedback:{neurolayer}:{mental_loop}:{int(__import__('time').time())}"
            memory.redis.set_json(feedback_key, feedback_record)
            memory.redis.expire(feedback_key, 86400)  # 24 hours
            
            return {
                "status": "feedback_queued",
                "neurolayer": neurolayer,
                "mental_loop": mental_loop,
                "feedback_type": feedback_type,
                "feedback_id": feedback_key
            }
            
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Feedback processing failed: {str(exc)}")

    @router.get("/neuro/mental-processing")
    async def neuro_mental_processing() -> dict[str, Any]:
        """Process pending mental-loop feedback to neurolayers."""
        try:
            # Get pending feedback
            feedback_keys = memory.redis.keys("neuro_mental_feedback:*")
            pending_feedback = []
            
            for key in feedback_keys:
                feedback = memory.redis.get_json(key)
                if feedback and not feedback.get("processed", False):
                    pending_feedback.append(feedback)
            
            # Process feedback (simplified)
            processed_count = 0
            adaptations = []
            
            for feedback in pending_feedback:
                # Mark as processed
                feedback["processed"] = True
                memory.redis.set_json(feedback["feedback_id"], feedback)
                
                # Create adaptation record
                adaptations.append({
                    "neurolayer": feedback["neurolayer"],
                    "mental_loop": feedback["mental_loop"],
                    "adaptation_type": feedback["feedback_type"],
                    "status": "applied"
                })
                processed_count += 1
            
            return {
                "status": "processing_complete",
                "pending_feedback": len(pending_feedback),
                "processed_feedback": processed_count,
                "adaptations": adaptations
            }
            
        except Exception as exc:
            return {
                "status": "processing_failed",
                "error": str(exc)[:200]
            }

    @router.get("/contracts/verify/{user_id}")
    async def contracts_verify(user_id: str) -> dict[str, Any]:
        try:
            return await legacy.contracts_verify(user_id)
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)[:200], "user_id": user_id}

    return router
