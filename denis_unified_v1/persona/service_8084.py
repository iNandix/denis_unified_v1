"""DENIS Persona Runtime: Thin handler over unified kernel (scheduler->plan->router).

P1.3 + P2 Integration:
- Mode selection: clarify/actions_plan/direct_local/direct_boosted
- LocalResponder fallback when boosters not allowed
- Engine probe pre/post for health reporting
- Actions execution with reentry on failure
- Outcome recording for CatBoost
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="DENIS Persona Runtime", version="1.1-P2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from denis_unified_v1.kernel.scheduler import get_model_scheduler
from denis_unified_v1.inference.router import InferenceRouter
from denis_unified_v1.telemetry.outcome_recorder import OutcomeRecorder
from denis_unified_v1.cognition.local_responder import create_local_responder
from denis_unified_v1.cognition.executor import Executor, Evaluator, ReentryController
from denis_unified_v1.cognition.tools import build_tool_registry
from denis_unified_v1.kernel.ops.engine_probe import run_engine_probe
from denis_unified_v1.kernel.engine_registry import get_engine_registry
from denis_unified_v1.kernel.internet_health import get_internet_health
from denis_unified_v1.telemetry.outcome_recorder import (
    select_mode,
    get_internet_status,
    get_allow_boosters,
    ExecutionMode,
    ConfidenceBand,
)
from denis_unified_v1.intent.unified_parser import parse_intent
from denis_unified_v1.catalog.tool_catalog import get_tool_catalog, CatalogContext
from denis_unified_v1.delivery import DeliverySubgraph
from denis_unified_v1.delivery.events_v1 import (
    RenderTextDeltaV1,
    RenderVoiceCancelledV1,
    DeliveryTextDeltaV1,
    DeliveryInterruptV1,
)
from denis_unified_v1.delivery.graph_projection import get_voice_projection


MAX_REENTRY = 2

# Seed voice pipeline topology in graph at import time (idempotent)
try:
    get_voice_projection().seed_topology()
    get_voice_projection().seed_engines()
except Exception:
    pass  # fail-open


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    group_id: str = "default"
    session_id: str | None = None
    voice_enabled: bool = False


router = InferenceRouter()
scheduler = get_model_scheduler()
outcome_recorder = OutcomeRecorder()
local_responder = create_local_responder()
executor = Executor(tool_registry=build_tool_registry())
evaluator = Evaluator()
reentry_controller = ReentryController()


@app.get("/meta")
async def meta():
    return {"status": "ok", "version": "1.1-P2", "service": "denis-persona"}


@app.get("/render/voice/segment")
async def get_voice_segment(request_id: str, segment_id: str = ""):
    """Serve cached voice segment as WAV for HASS media_player."""
    from denis_unified_v1.delivery.voice_cache import get_voice_cache
    import io
    import wave

    cache = get_voice_cache()

    if segment_id:
        seg = await cache.get_segment(request_id, segment_id)
    else:
        seg = await cache.get_latest_segment(request_id)

    if not seg:
        return {"error": "segment not found"}, 404

    if seg.is_cancelled:
        return {"error": "segment cancelled"}, 410

    if not seg.pcm_bytes:
        return {"error": "no audio data"}, 404

    # Convert PCM to WAV
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(seg.channels)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(seg.sample_rate)
        wav.writeframes(seg.pcm_bytes)

    wav_bytes = buf.getvalue()

    from starlette.responses import Response

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f"inline; filename=voice_{segment_id or request_id}.wav"
        },
    )


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """Persona chat: P1.3 + P2 mode selection + execution with reentry."""
    return await _chat(req)


@app.post("/v1/chat")
async def chat_v1(req: ChatRequest) -> dict[str, Any]:
    """Alias for /chat - API v1 compatible."""
    return await _chat(req)


@app.websocket("/chat")
async def chat_ws(websocket: WebSocket):
    """WS: single output stream via DeliverySubgraph with voice support."""
    await websocket.accept()
    print("WS: accepted connection")

    # Track cancel events and deliveries per request
    cancel_events: dict[str, asyncio.Event] = {}
    active_deliveries: dict[str, Any] = {}

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                print(
                    f"WS: Received: type={data.get('type')}, request_id={data.get('request_id')}",
                    flush=True,
                )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"WS: receive error: {e}", flush=True)
                break

            # Handle client.interrupt - propagate to active delivery
            if data.get("type") == "client.interrupt":
                print(f"WS: Received client.interrupt event: {data}")
                request_id = data.get("request_id")
                print(f"[INTERRUPT] cancel_events keys: {list(cancel_events.keys())}")
                print(
                    f"[INTERRUPT] active_deliveries keys: {list(active_deliveries.keys())}"
                )
                if request_id and request_id in cancel_events:
                    print(f"[INTERRUPT] Setting cancel event for {request_id}")
                    cancel_events[request_id].set()

                    # Propagate to active delivery if exists
                    if request_id in active_deliveries:
                        print(
                            f"[INTERRUPT] Propagating to active delivery for {request_id}"
                        )
                        delivery = active_deliveries[request_id]
                        try:
                            interrupt_events = await delivery.handle_interrupt(
                                DeliveryInterruptV1(
                                    request_id=request_id, reason="user_interrupt"
                                )
                            )
                            print(
                                f"[INTERRUPT] Got {len(interrupt_events)} events from handle_interrupt: {interrupt_events}"
                            )
                            for ev in interrupt_events:
                                await websocket.send_json(ev)
                        except Exception as e:
                            print(f"[INTERRUPT] Error propagating: {e}")
                    else:
                        print(
                            f"[INTERRUPT] request_id {request_id} NOT in active_deliveries"
                        )
                continue

            # Get voice_enabled from client if present
            voice_enabled = data.get("voice_enabled", False)

            request_id = (
                data.get("request_id")
                or f"req_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            )
            user_text = data.get("message", data.get("text", ""))

            # Create cancel event for this request
            cancel_event = asyncio.Event()
            cancel_events[request_id] = cancel_event

            # Create subgraph for this request
            delivery = DeliverySubgraph(
                voice_enabled=voice_enabled,
                tts_provider="piper_stream" if voice_enabled else "none",
                piper_base_url="http://10.10.10.2:8005",
            )
            active_deliveries[request_id] = delivery

            # Project request to graph
            try:
                get_voice_projection().project_voice_request(
                    request_id=request_id,
                    voice_enabled=voice_enabled,
                    user_id=data.get("user_id", "default"),
                )
            except Exception:
                pass  # fail-open

            # Send initial ack immediately (TTFC)
            seq = 0
            await websocket.send_json(
                {
                    "request_id": request_id,
                    "type": "render.text.delta",
                    "sequence": seq,
                    "payload": {"text": ""},
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )
            seq += 1

            # Get response from persona pipeline (non-blocking with interrupt support)
            # Pattern A: WS loop never blocks - reads messages while pipeline runs
            accumulated_text = ""
            task_seq = seq
            cancel_event = cancel_events.get(request_id)
            interrupted = False

            try:
                req = ChatRequest(
                    message=user_text, user_id=data.get("user_id", "default")
                )

                async def run_pipeline():
                    nonlocal accumulated_text

                    # Set narrative callback for personality
                    narrative_events = []

                    def emit_narrative(event):
                        narrative_events.append(event)

                    executor.set_emit_callback(emit_narrative)

                    result = await _chat(req)
                    accumulated_text = result.get("response", "")

                    # Send narrative events from executor (personality)
                    for ev in narrative_events:
                        ev["request_id"] = request_id
                        await websocket.send_json(ev)

                    if voice_enabled and delivery and accumulated_text:
                        text_delta = DeliveryTextDeltaV1(
                            request_id=request_id,
                            text_delta=accumulated_text,
                            is_final=True,
                            sequence=task_seq,
                        )
                        events = await delivery.handle_text_delta(text_delta)
                        for ev in events:
                            await websocket.send_json(ev)

                    await websocket.send_json(
                        {
                            "request_id": request_id,
                            "type": "render.text.final",
                            "sequence": task_seq + 1,
                            "payload": {"text": accumulated_text},
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }
                    )

                # Start pipeline in background - WS loop stays free
                voice_task = asyncio.create_task(run_pipeline())

                # WS loop: keep reading messages while pipeline runs
                # This allows receiving client.interrupt at any time
                while not voice_task.done():
                    try:
                        # Wait for next message with timeout to check task periodically
                        msg_data = await asyncio.wait_for(
                            websocket.receive_json(), timeout=0.1
                        )

                        print(f"[WS_LOOP] Received msg: {msg_data}", flush=True)

                        # Handle interrupt immediately - don't wait for task
                        if msg_data.get("type") == "client.interrupt":
                            print(f"[WS_LOOP] INTERRUPT DETECTED: {msg_data}")
                            # ALWAYS propagate to delivery, regardless of cancel_events
                            if delivery:
                                print(
                                    f"[WS_LOOP] Calling delivery.handle_interrupt for {request_id}"
                                )
                                try:
                                    interrupt_events = await delivery.handle_interrupt(
                                        DeliveryInterruptV1(
                                            request_id=request_id,
                                            reason="user_interrupt",
                                        )
                                    )
                                    print(
                                        f"[WS_LOOP] Got {len(interrupt_events)} events from handle_interrupt"
                                    )
                                    for ev in interrupt_events:
                                        print(
                                            f"[WS_LOOP] Sending event: {ev.get('type')}"
                                        )
                                        await websocket.send_json(ev)
                                except Exception as e:
                                    print(f"[WS_LOOP] Error in handle_interrupt: {e}")

                            interrupted = True
                            break

                    except asyncio.TimeoutError:
                        # Check if interrupt was set via cancel_event
                        if cancel_event and cancel_event.is_set():
                            print(f"[INTERRUPT] Cancel event set, breaking loop")
                            interrupted = True
                            break
                        continue
                    except Exception as e:
                        print(f"WS: receive error in loop: {e}")
                        break

                # Wait for pipeline to complete (or cancelled)
                if not voice_task.done():
                    voice_task.cancel()
                    try:
                        await voice_task
                    except asyncio.CancelledError:
                        pass

                # Get metrics and send outcome
                voice_metrics = {}
                if voice_enabled and delivery:
                    voice_metrics = delivery.get_metrics(request_id)

                await websocket.send_json(
                    {
                        "request_id": request_id,
                        "type": "render.outcome",
                        "sequence": task_seq + 2,
                        "payload": {
                            "mode": "direct",
                            "reason_codes": ["voice_enabled"]
                            if voice_enabled
                            else ["voice_disabled"],
                            "response_length": len(accumulated_text),
                            "voice_ttfc_ms": voice_metrics.get("voice_ttfc_ms", 0),
                            "tts_backend": voice_metrics.get("tts_backend", "none"),
                            "voice_cancelled": voice_metrics.get(
                                "voice_cancelled", False
                            ),
                            "cancel_latency_ms": voice_metrics.get(
                                "cancel_latency_ms", 0
                            ),
                            "bytes_streamed": voice_metrics.get("bytes_streamed", 0),
                            "audio_duration_ms": voice_metrics.get(
                                "audio_duration_ms", 0
                            ),
                        },
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                )

                # Project outcome to graph
                try:
                    get_voice_projection().project_outcome(
                        request_id=request_id,
                        metrics=voice_metrics,
                    )
                except Exception:
                    pass  # fail-open

            except Exception as e:
                print(f"WS: processing error: {e}")
                await websocket.send_json(
                    {
                        "request_id": request_id,
                        "type": "error",
                        "sequence": seq,
                        "payload": {"error": str(e)},
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                )

            # Cleanup
            if request_id in cancel_events:
                del cancel_events[request_id]

    except Exception as e:
        print(f"WS error: {e}")
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass
    finally:
        print("WS: connection closed")


@app.websocket("/v1/chat")
async def chat_ws_v1(websocket: WebSocket):
    """WebSocket alias for /v1/chat."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            req = ChatRequest(**data)
            result = await _chat(req)
            await websocket.send_json(result)
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass


async def _chat(req: ChatRequest) -> dict[str, Any]:
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8084)
