"""Memory API routes for phase-9 unified memory rollout."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from denis_unified_v1.memory import build_memory_manager
from denis_unified_v1.memory.legacy_client import LegacyMemoryClient


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

    @router.get("/mental-loop/levels")
    async def mental_loop_levels() -> dict[str, Any]:
        return {"levels": MENTAL_LOOP_LEVELS}

    @router.post("/cot/adaptive")
    async def adaptive_cot(req: AdaptiveCoTRequest) -> dict[str, Any]:
        return _adaptive_cot(
            query=req.query,
            latency_budget_ms=req.latency_budget_ms,
            context_window_tokens=req.context_window_tokens,
        )

    @router.get("/contracts/verify/{user_id}")
    async def contracts_verify(user_id: str) -> dict[str, Any]:
        try:
            return await legacy.contracts_verify(user_id)
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)[:200], "user_id": user_id}

    return router
