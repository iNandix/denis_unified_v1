"""DENIS Persona Runtime: Thin handler over unified kernel (scheduler->plan->router).

P1.3 + P2 Integration:
- Mode selection: clarify/actions_plan/direct_local/direct_boosted
- LocalResponder fallback when boosters not allowed
- Engine probe pre/post for health reporting
- Actions execution with reentry on failure
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
from denis_unified_v1.cognition.executor import Executor, Evaluator, ReentryController, save_toolchain_log
from denis_unified_v1.cognition.tools import build_tool_registry
from denis_unified_v1.kernel.ops.engine_probe import run_engine_probe
from denis_unified_v1.catalog.tool_catalog import get_tool_catalog, CatalogContext


MAX_REENTRY = 2


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    group_id: str = "default"


app = FastAPI(title="DENIS Persona Runtime", version="1.1-P2")

router = InferenceRouter()
scheduler = get_model_scheduler()
outcome_recorder = OutcomeRecorder()
local_responder = create_local_responder()
executor = Executor(tool_registry=build_tool_registry())
evaluator = Evaluator()
reentry_controller = ReentryController()


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """Persona chat: P1.3 + P2 mode selection + execution with reentry."""
    request_id = str(uuid.uuid4())
    text = req.message

    # P2: Engine probe pre-execution
    probe_pre = run_engine_probe(mode="ping", timeout_ms=800)

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

    # P1.3: Dynamic Tool Catalog lookup (exists vs create)
    tool_catalog = get_tool_catalog()
    catalog_ctx = CatalogContext(
        request_id=request_id,
        allow_boosters=allow_boosters,
        internet_gate=internet_status == "up",
        booster_health=internet_status == "up",
        confidence_band=intent_result.confidence_band,
        meta={"user_id": req.user_id, "group_id": req.group_id},
    )
    catalog_lookup = tool_catalog.lookup(
        intent=intent_str,
        entities={"user_id": req.user_id, "group_id": req.group_id},
        ctx=catalog_ctx,
    )

    # Add catalog decision to reason_codes
    if catalog_lookup.exists_vs_create == "exists":
        reason_codes = ["capability_exists"]
        reason_codes.extend(
            [f"tool_selected:{m.name}" for m in catalog_lookup.matched_tools[:3]]
        )
    elif catalog_lookup.exists_vs_create == "compose":
        reason_codes = ["capability_partial_compose", "tool_composed"]
        reason_codes.extend(
            [f"tool_selected:{m.name}" for m in catalog_lookup.matched_tools[:3]]
        )
    elif catalog_lookup.exists_vs_create == "create":
        reason_codes = ["capability_missing", "capability_created"]
    else:
        reason_codes = ["needs_clarification"]

    # P1.3: Mode selection
    confidence_band = ConfidenceBand(intent_result.confidence_band)
    selected_mode, mode_reason_codes = select_mode(
        confidence_band,
        intent_str,
        internet_status,
        allow_boosters,
    )
    reason_codes.extend(mode_reason_codes)

    degraded = selected_mode in [ExecutionMode.DIRECT_DEGRADED_LOCAL]

    result: dict[str, Any] = {"response": "", "meta": {}}
    error: str | None = None

    try:
        # Execute with reentry (P2)
        result = await _execute_with_reentry(
            request_id=request_id,
            text=text,
            req=req,
            intent_result=intent_result,
            intent_str=intent_str,
            selected_mode=selected_mode,
            reason_codes=reason_codes,
            degraded=degraded,
            internet_status=internet_status,
            allow_boosters=allow_boosters,
        )
    except Exception as e:
        error = str(e)
        result = {
            "response": "Error interno en Persona. Por favor, inténtalo de nuevo.",
            "meta": {
                "request_id": request_id,
                "error": error,
                "degraded": True,
            },
        }

    # P2: Engine probe post-execution
    probe_post = run_engine_probe(mode="ping", timeout_ms=800)

    # Add probe results to meta
    if result and "meta" in result:
        result["meta"]["probe_pre"] = probe_pre
        result["meta"]["probe_post"] = probe_post

    # P1.3: Record outcome (ALWAYS - even on error)
    outcome_recorder.record(
        request_id=request_id,
        intent_result=intent_result,
        internet_status=internet_status,
        selected_mode=selected_mode,
        allow_boosters=allow_boosters,
        degraded=degraded or error is not None,
        reason_codes=reason_codes + (["error:" + error] if error else []),
        catalog_features=catalog_lookup.features,
    )

    return result


async def _execute_with_reentry(
    request_id: str,
    text: str,
    req: ChatRequest,
    intent_result: Any,
    intent_str: str,
    selected_mode: ExecutionMode,
    reason_codes: list,
    degraded: bool,
    internet_status: InternetStatus,
    allow_boosters: bool,
) -> dict[str, Any]:
    """Execute with reentry on failure (P2)."""

    iteration = 0

    while iteration < MAX_REENTRY:
        iteration += 1

        if selected_mode == ExecutionMode.DIRECT_BOOSTED:
            result = await _execute_boosted(request_id, text, req)
        elif selected_mode == ExecutionMode.ACTIONS_PLAN:
            result = await _execute_actions_plan(request_id, text, req, intent_result)
        elif selected_mode == ExecutionMode.CLARIFY:
            result = _execute_clarify(text, intent_result)
        else:
            result = await _execute_local(
                request_id,
                text,
                req,
                intent_result,
                internet_status,
                allow_boosters,
                selected_mode,
            )

        # Check if we need to reentry
        if iteration >= MAX_REENTRY:
            break

        # Evaluate result and decide reentry
        if "degraded" in result.get("meta", {}) and result["meta"]["degraded"]:
            # Already degraded, no point reentering
            break

        # For actions_plan, check if steps failed
        if selected_mode == ExecutionMode.ACTIONS_PLAN:
            step_results = result.get("meta", {}).get("step_results", [])
            failed_steps = [s for s in step_results if s.get("status") == "failed"]

            if failed_steps and iteration < MAX_REENTRY:
                reason_codes.append(f"reentry_iteration_{iteration}")
                # Reentry: try with different plan or fallback
                selected_mode = ExecutionMode.DIRECT_LOCAL
                continue

        break

    result["meta"]["iteration"] = iteration
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
    """Execute via actions plan with executor (P2)."""
    intent_v1 = Intent_v1(
        intent=intent_result.intent.value
        if hasattr(intent_result.intent, "value")
        else str(intent_result.intent),
        confidence=intent_result.confidence,
        confidence_band=intent_result.confidence_band,
    )

    candidates = generate_candidate_plans(intent_v1)
    selected_plan = select_plan(candidates, intent_result.confidence_band)

    if not selected_plan:
        return {
            "response": "No se pudo generar un plan de acciones.",
            "meta": {"request_id": request_id, "mode": "actions_plan", "plan_id": None},
        }

    # Execute plan with executor (P2)
    context = {
        "user_message": text,
        "session_id": f"persona_{req.user_id}_{req.group_id}",
    }

    execution_result = executor.execute_plan(selected_plan, context)

    # P1.3: Save toolchain step log (mandatory per plan execution)
    reports_dir = outcome_recorder.reports_dir
    save_toolchain_log(execution_result, reports_dir, request_id)

    # Evaluate execution
    evaluation = evaluator.evaluate(
        selected_plan,
        execution_result,
        intent_result.acceptance_criteria or [],
    )

    # Build response from execution
    steps_summary = []
    for sr in execution_result.step_results:
        steps_summary.append(
            {
                "step_id": sr.step_id,
                "status": sr.status.value
                if hasattr(sr.status, "value")
                else str(sr.status),
                "duration_ms": sr.duration_ms,
            }
        )

    response_text = _build_actions_response(execution_result, evaluation)

    return {
        "response": response_text,
        "meta": {
            "request_id": request_id,
            "mode": "actions_plan",
            "plan_id": selected_plan.candidate_id,
            "steps": steps_summary,
            "evaluation_score": evaluation.score,
            "evaluation_passed": evaluation.passed,
            "degraded": execution_result.status == "degraded",
        },
    }


def _build_actions_response(execution_result: Any, evaluation: Any) -> str:
    """Build response from actions execution."""
    if execution_result.status == "success":
        completed = len(execution_result.step_results)
        return f"Se completaron {completed} operaciones."
    elif execution_result.status == "degraded":
        return f"Se completaron algunas operaciones con degraded: {execution_result.degraded_reason or 'sin detalles'}"
    else:
        return f"No se pudieron completar las operaciones: {execution_result.reason_code or 'error desconocido'}"


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
        "version": "v1.1-P2",
        "registry_hash": hash(json.dumps(registry, sort_keys=True)),
        "internet_status": internet_status,
        "allow_boosters": allow_boosters,
        "engine_summary": {
            "total": len(engines),
            "locals": locals_count,
            "boosters": boosters_count,
        },
        "max_reentry": MAX_REENTRY,
        "uptime_sec": 0,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8084)
