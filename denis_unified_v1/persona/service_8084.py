"""DENIS Persona Runtime: Thin handler over unified kernel (scheduler->plan->router).

P1.3 Integration:
- Mode selection: clarify/actions_plan/direct_local/direct_boosted
- LocalResponder fallback when boosters not allowed
- Outcome recording for CatBoost
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from denis_unified_v1.kernel.scheduler import get_model_scheduler, InferenceRequest
from denis_unified_v1.inference.router import InferenceRouter
from denis_unified_v1.kernel.engine_registry import get_engine_registry
from denis_unified_v1.kernel.internet_health import get_internet_health
from denis_unified_v1.actions.planner import generate_candidate_plans, select_plan
from denis_unified_v1.actions.models import Intent_v1
from denis_unified_v1.intent.unified_parser import parse_intent
from denis_unified_v1.telemetry.outcome_recorder import (
    OutcomeRecorder,
    ExecutionMode,
    InternetStatus,
    ConfidenceBand,
    select_mode,
    get_internet_status,
    get_allow_boosters,
)
from denis_unified_v1.cognition.local_responder import create_local_responder


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    group_id: str = "default"


app = FastAPI(title="DENIS Persona Runtime", version="1.1")

router = InferenceRouter()
scheduler = get_model_scheduler()
outcome_recorder = OutcomeRecorder()
local_responder = create_local_responder()


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """Persona chat: P1.3 mode selection + execution."""
    request_id = str(uuid.uuid4())
    text = req.message

    # P1.3: Get internet status and boosters policy
    internet_status = get_internet_status()
    allow_boosters = get_allow_boosters()

    # P1.3: Intent detection
    intent_result = parse_intent(text)
    intent_str = (
        intent_result.intent.value
        if hasattr(intent_result.intent, "value")
        else str(intent_result.intent)
    )

    # P1.3: Mode selection
    confidence_band = ConfidenceBand(intent_result.confidence_band)
    selected_mode, reason_codes = select_mode(
        confidence_band,
        intent_str,
        internet_status,
        allow_boosters,
    )

    degraded = selected_mode in [ExecutionMode.DIRECT_DEGRADED_LOCAL]

    # Execute based on mode
    if selected_mode == ExecutionMode.DIRECT_BOOSTED:
        # Normal path: use scheduler + router
        result = await _execute_boosted(request_id, text, req)
    elif selected_mode == ExecutionMode.ACTIONS_PLAN:
        # Execute via actions plan
        result = await _execute_actions_plan(request_id, text, req, intent_result)
    elif selected_mode == ExecutionMode.CLARIFY:
        # Low confidence: ask clarification
        result = _execute_clarify(text, intent_result)
    else:
        # Direct local or degraded: use LocalResponder
        result = await _execute_local(
            request_id,
            text,
            req,
            intent_result,
            internet_status,
            allow_boosters,
            selected_mode,
        )

    # P1.3: Record outcome
    outcome_recorder.record(
        request_id=request_id,
        intent_result=intent_result,
        internet_status=internet_status,
        selected_mode=selected_mode,
        allow_boosters=allow_boosters,
        degraded=degraded,
        reason_codes=reason_codes,
    )

    return result


async def _execute_boosted(
    request_id: str, text: str, req: ChatRequest
) -> dict[str, Any]:
    """Execute via scheduler + router (normal path)."""
    inference_request = InferenceRequest(
        request_id=request_id,
        session_id=f"persona_{req.user_id}_{req.group_id}",
        route_type="fast_talk",
        task_type="chat",
        payload={"max_tokens": 512, "temperature": 0.7},
    )

    plan = scheduler.assign(inference_request)
    messages = [{"role": "user", "content": text}]

    result = await router.route_chat(
        messages=messages,
        request_id=request_id,
        inference_plan=plan,
    )

    return {
        "response": result.get("response", ""),
        "meta": {
            "request_id": request_id,
            "llm_used": result.get("llm_used"),
            "engine_id": result.get("engine_id"),
            "model_selected": result.get("model_selected"),
            "latency_ms": result.get("latency_ms"),
            "input_tokens": result.get("input_tokens"),
            "output_tokens": result.get("output_tokens"),
            "cost_usd": result.get("cost_usd"),
            "fallback_used": result.get("fallback_used"),
            "attempts": result.get("attempts"),
            "degraded": result.get("degraded"),
            "skipped_engines": result.get("skipped_engines"),
            "internet_status": result.get("internet_status"),
        },
    }


async def _execute_actions_plan(
    request_id: str, text: str, req: ChatRequest, intent_result: Any
) -> dict[str, Any]:
    """Execute via actions plan."""
    intent_v1 = Intent_v1(
        intent=intent_result.intent.value
        if hasattr(intent_result.intent, "value")
        else str(intent_result.intent),
        confidence=intent_result.confidence,
        confidence_band=intent_result.confidence_band,
    )

    candidates = generate_candidate_plans(intent_v1)
    selected_plan = select_plan(candidates, intent_result.confidence_band)

    # TODO: Execute plan with executor
    # For now, return a placeholder

    return {
        "response": f"[Actions plan: {selected_plan.candidate_id if selected_plan else 'none'}]",
        "meta": {
            "request_id": request_id,
            "mode": "actions_plan",
            "plan_id": selected_plan.candidate_id if selected_plan else None,
            "degraded": False,
        },
    }


def _execute_clarify(text: str, intent_result: Any) -> dict[str, Any]:
    """Return clarification response for low confidence."""
    clarification = (
        "Para ayudarte mejor, necesito más contexto. "
        "¿Qué necesitas exactamente? (debuggear, ejecutar tests, implementar feature, etc.)"
    )

    if intent_result.needs_clarification:
        clarification = intent_result.needs_clarification[0]
    elif intent_result.two_plans_required:
        clarification = (
            "Veo dos posibles interpretaciones: "
            "1) Necesitas debuggear un error "
            "2) Necesitas ejecutar tests "
            "¿Cuál se acerca más?"
        )

    return {
        "response": clarification,
        "meta": {
            "mode": "clarify",
            "confidence": intent_result.confidence,
            "confidence_band": intent_result.confidence_band,
        },
    }


async def _execute_local(
    request_id: str,
    text: str,
    req: ChatRequest,
    intent_result: Any,
    internet_status: InternetStatus,
    allow_boosters: bool,
    mode: ExecutionMode,
) -> dict[str, Any]:
    """Execute via LocalResponder (offline/degraded path)."""
    intent_str = (
        intent_result.intent.value
        if hasattr(intent_result.intent, "value")
        else str(intent_result.intent)
    )

    local_response = await local_responder.respond(
        user_message=text,
        intent=intent_str,
        confidence=intent_result.confidence,
        internet_status=internet_status,
        allow_boosters=allow_boosters,
    )

    return {
        "response": local_response.response,
        "meta": {
            "request_id": request_id,
            "mode": local_response.mode.value
            if hasattr(local_response.mode, "value")
            else str(local_response.mode),
            "degraded": local_response.degraded,
            "reason_codes": local_response.reason_codes,
            "retrieval_used": local_response.retrieval_used,
            "llm_used": local_response.llm_used,
        },
    }


@app.get("/meta")
async def meta() -> dict[str, Any]:
    """Health/meta endpoint for ops and debugging."""
    registry = get_engine_registry()
    internet_status = get_internet_health().check()
    allow_boosters = get_allow_boosters()
    engines = list(registry.keys())
    locals_count = sum(1 for e in registry.values() if "local" in e.get("tags", []))
    boosters_count = sum(
        1 for e in registry.values() if "internet_required" in e.get("tags", [])
    )

    return {
        "version": "v1.1-P1.3",
        "registry_hash": hash(json.dumps(registry, sort_keys=True)),
        "internet_status": internet_status,
        "allow_boosters": allow_boosters,
        "engine_summary": {
            "total": len(engines),
            "locals": locals_count,
            "boosters": boosters_count,
        },
        "uptime_sec": 0,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8084)
