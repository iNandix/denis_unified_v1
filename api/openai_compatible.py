"""OpenAI-compatible chat endpoints for Denis incremental API layer."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import time
import uuid
from typing import Any
import logging

import aiohttp
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from denis_unified_v1.kernel.scheduler import get_model_scheduler, InferenceRequest
from denis_unified_v1.inference.hop import parse_hop, set_current_hop, reset as reset_hop
from .sse_handler import sse_event


# Canary switch for unified kernel migration
# DENIS_PERSONA_UNIFIED=1 -> Use new unified kernel (scheduler + router)
# DENIS_PERSONA_UNIFIED=0 -> Use legacy handler (if available)
_USE_UNIFIED_KERNEL = os.getenv("DENIS_PERSONA_UNIFIED", "1") == "1"


def _utc_now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _openai_chunk(
    *,
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None,
) -> dict[str, Any]:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(created),
        "model": str(model),
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _iter_text_chunks(text: str, *, chunk_chars: int = 64):
    raw = text or ""
    n = max(1, int(chunk_chars))
    for i in range(0, len(raw), n):
        yield raw[i : i + n]


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    # Default to persona for external clients (e.g., OpenCode).
    model: str = "denis-persona"
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class _ChatHandler:
    """Simplified chat handler that works without SMX dependencies."""

    def __init__(self, flags: Any):
        self.flags = flags
        self.cognitive_router = None
        self.inference_router = None

    def _classify_prompt_injection(self, text: str) -> tuple[str, list[str]]:
        """Very simple prompt injection classification."""
        text_lower = text.lower()
        suspicious_patterns = [
            "ignore previous instructions",
            "system prompt",
            "developer mode",
            "jailbreak",
            "act as",
            "pretend you are",
        ]

        found_patterns = [p for p in suspicious_patterns if p in text_lower]

        if len(found_patterns) >= 3:
            return "high", found_patterns
        elif len(found_patterns) >= 1:
            return "medium", found_patterns
        else:
            return "low", []

    def _extract_user_text(self, messages: list[ChatMessage]) -> str:
        for msg in reversed(messages):
            if msg.role == "user" and isinstance(msg.content, str):
                return msg.content.strip()
        return ""

    def _inject_persona_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Prepend Denis persona + developer policy system blocks (best-effort)."""
        enabled = (os.getenv("DENIS_OPENAI_COMPAT_PERSONA") or "1").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if not enabled:
            return messages

        system_blob = "\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system"
        )

        persona_text = "Eres DENIS, un asistente de IA útil y directo."
        policy_text = "POLÍTICAS DE DESARROLLO: no inventes resultados ni ejecuciones."
        try:
            from denis_unified_v1.persona.message_composer import MessageComposer

            persona_text = MessageComposer.SYSTEM_PERSONA
            policy_text = MessageComposer.DEVELOPER_POLICY
        except Exception:
            pass  # fail-open: keep lightweight defaults

        blocks: list[dict[str, Any]] = []
        if "Eres DENIS" not in system_blob and "DENIS, un asistente" not in system_blob:
            blocks.append({"role": "system", "content": persona_text})
        if "POLÍTICAS DE DESARROLLO" not in system_blob and "POLITICAS DE DESARROLLO" not in system_blob:
            blocks.append({"role": "system", "content": policy_text})

        return blocks + messages if blocks else messages

    def _maybe_tool_call(self, req: ChatCompletionRequest, user_text: str) -> dict[str, Any] | None:
        if not req.tools:
            return None
        lowered = user_text.lower()
        if "tool" not in lowered and "perceive" not in lowered and "act" not in lowered:
            return None
        first = req.tools[0]
        fn = (first.get("function") or {}) if isinstance(first, dict) else {}
        fn_name = fn.get("name") if isinstance(fn, dict) else "denis_tool"
        return {
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": fn_name,
                "arguments": json.dumps({"text": user_text}),
            },
        }

    def _validate_output(self, content: str) -> tuple[str, dict[str, Any]]:
        """Valida la salida según Fase 10 (tamaño y secretos básicos)."""
        text = content or ""
        meta: dict[str, Any] = {"blocked": False, "reasons": []}

        # 1) Límite de longitud
        try:
            from observability.metrics import gate_output_blocked

            max_tokens = int(getattr(self.flags, "phase10_max_output_tokens", 512))
            max_chars = max_tokens * 8
            if len(text) > max_chars:
                meta["blocked"] = True
                meta["reasons"].append("length")
                gate_output_blocked.labels(reason="length").inc()
                safe_msg = "La respuesta completa es demasiado larga para las políticas actuales."
                return safe_msg, meta
        except Exception:
            max_tokens = 512
            max_chars = max_tokens * 8
            if len(text) > max_chars:
                meta["blocked"] = True
                meta["reasons"].append("length")
                safe_msg = "La respuesta completa es demasiado larga para las políticas actuales."
                return safe_msg, meta

        # 2) Búsqueda de patrones sensibles
        lower = text.lower()
        secret_markers = [
            "begin private key",
            "aws_secret_access_key",
            ".env",
            "ssh-rsa",
        ]
        for marker in secret_markers:
            if marker in lower:
                meta["blocked"] = True
                meta["reasons"].append("secret_pattern")
                try:
                    from observability.metrics import gate_output_blocked

                    gate_output_blocked.labels(reason="secret_pattern").inc()
                except Exception:
                    pass
                safe_msg = "El modelo generó contenido que parece incluir secretos o claves."
                return safe_msg, meta

        return text, meta

    async def _try_legacy_chat(self, user_text: str) -> str | None:
        """Try to get response from legacy endpoint."""
        endpoints = [
            os.getenv("DENIS_LEGACY_8084", "http://127.0.0.1:8084/v1/chat"),
            os.getenv("DENIS_LEGACY_8085", "http://127.0.0.1:8085/v1/chat"),
        ]

        timeout = aiohttp.ClientTimeout(total=5.0)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for endpoint in endpoints:
                    try:
                        payload = {"message": user_text}
                        async with session.post(endpoint, json=payload) as resp:
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                if isinstance(data, dict):
                                    for key in (
                                        "response",
                                        "answer",
                                        "text",
                                        "content",
                                    ):
                                        val = data.get(key)
                                        if isinstance(val, str) and val.strip():
                                            return val.strip()
                    except Exception:
                        continue
        except Exception:
            pass

        return None

    async def _generate_legacy(
        self,
        req: ChatCompletionRequest,
        completion_id: str,
        user_text: str,
        prompt_tokens: int,
    ) -> dict[str, Any]:
        """Legacy handler - raises NotImplementedError as no legacy handler exists."""
        raise NotImplementedError(
            "Legacy handler not available. Set DENIS_PERSONA_UNIFIED=1 to use unified kernel."
        )

    async def generate(self, req: ChatCompletionRequest) -> dict[str, Any]:
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        user_text = self._extract_user_text(req.messages)
        prompt_tokens = max(1, len(user_text.split()))

        # Canary switch: use legacy handler if DENIS_PERSONA_UNIFIED=0
        if not _USE_UNIFIED_KERNEL:
            try:
                # Try to use legacy handler if available
                return await self._generate_legacy(req, completion_id, user_text, prompt_tokens)
            except Exception as e:
                # Log fallback and continue with unified kernel
                print(f"WARN: Legacy handler failed ({e}), falling back to unified kernel")

        # Prompt injection guard
        risk, risk_reasons = self._classify_prompt_injection(user_text)
        try:
            from observability.metrics import gate_prompt_injection

            gate_prompt_injection.labels(risk=risk).inc()
        except Exception:
            pass

        high_risk = risk == "high" and getattr(
            self.flags, "phase10_enable_prompt_injection_guard", False
        )

        if high_risk:
            return {
                "id": completion_id,
                "object": "chat.completion",
                "created": _utc_now(),
                "model": req.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Request blocked due to prompt injection risk.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": 0,
                    "total_tokens": prompt_tokens,
                },
                "meta": {"path": "blocked", "risk": risk, "reasons": risk_reasons},
            }

        tool_call = self._maybe_tool_call(req, user_text)
        if tool_call:
            return {
                "id": completion_id,
                "object": "chat.completion",
                "created": _utc_now(),
                "model": req.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": 0,
                    "total_tokens": prompt_tokens,
                },
                "meta": {"path": "tool_calls"},
            }

        # Get InferencePlan from scheduler (no double routing)
        scheduler = get_model_scheduler()
        inference_request = InferenceRequest(
            request_id=completion_id,
            session_id="session_123",  # Dummy, can be from context
            route_type="fast_talk",  # Derive from req or cognitive_router, default fast_talk
            task_type="chat",
            payload={
                "max_tokens": req.max_tokens or 512,
                "temperature": req.temperature or 0.7,
            },
        )
        inference_plan = scheduler.assign(inference_request)

        # P4: Always use InferenceRouter (plan-first), never router_v2
        from denis_unified_v1.inference.router import InferenceRouter

        if self.inference_router is None:
            self.inference_router = InferenceRouter()

        try:
            messages_payload: list[dict[str, Any]] = [
                {"role": msg.role, "content": str(msg.content or "")} for msg in req.messages
            ]
            messages_payload = self._inject_persona_messages(messages_payload)
            routed = await self.inference_router.route_chat(
                messages=messages_payload,
                request_id=completion_id,
                inference_plan=inference_plan,
            )
            answer = str(routed.get("response") or "").strip()
            path = f"inference_router:{routed.get('llm_used', 'unknown')}"
            router_meta = {
                "llm_used": routed.get("llm_used"),
                "engine_id": routed.get("engine_id"),
                "latency_ms": routed.get("latency_ms"),
                "cost_usd": routed.get("cost_usd"),
                "fallback_used": routed.get("fallback_used"),
                "attempts": routed.get("attempts"),
                "model_selected": routed.get("model_selected"),
                "skipped_engines": routed.get("skipped_engines"),
                "internet_status": routed.get("internet_status"),
                "degraded": routed.get("degraded"),
                "inference_plan_applied": inference_plan is not None,
            }
        except Exception as exc:
            # No silent legacy fallback — surface the real error
            answer = f"Denis inference failed: {type(exc).__name__}: {str(exc)[:200]}"
            path = "inference_error"
            router_meta = {"error": str(exc)[:300]}

        # Validación de salida
        validated_answer, validation_meta = self._validate_output(answer)
        completion_tokens = max(1, len(validated_answer.split()))

        # Record execution result in cognitive router if available
        if self.cognitive_router is not None and inference_plan is not None:
            try:
                self.cognitive_router.record_execution_result(
                    request_id=completion_id,
                    tool_name="inference_router",  # Or from plan
                    success=bool(validated_answer),
                    error=None if validated_answer else "no_response",
                    execution_time_ms=router_meta.get("latency_ms", 0),
                    metadata={
                        "path": path,
                        "router_meta": router_meta,
                        "validation": validation_meta,
                    },
                )
            except Exception:
                pass

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": _utc_now(),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": validated_answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "meta": {
                "path": path,
                "router": router_meta,
                "output_validation": validation_meta,
                "prompt_injection": {
                    "risk": risk,
                    "reasons": risk_reasons,
                },
            },
        }


class DenisRuntime:
    """Simplified runtime that works without SMX dependencies."""

    def __init__(self):
        try:
            from feature_flags import load_feature_flags

            self.flags = load_feature_flags()
        except Exception:
            self.flags = type(
                "Flags",
                (),
                {
                    "denis_use_voice_pipeline": False,
                    "denis_use_memory_unified": False,
                    "denis_use_atlas": False,
                    "denis_use_inference_router": False,
                    "phase10_enable_prompt_injection_guard": False,
                    "phase10_max_output_tokens": 512,
                },
            )()

        self.models = [
            {"id": "denis-persona", "object": "model"},
            {"id": "denis-cognitive", "object": "model"},
        ]
        self.budget_manager = None

    async def generate(self, req: ChatCompletionRequest) -> dict[str, Any]:
        """Generate response using available backends."""
        # Check for deterministic test mode - ONLY in non-production environments
        env = os.getenv("ENV", "production")  # Default to production for safety

        # Contract test mode: avoid external calls and return deterministic output.
        # Triggered by env-var in non-production; model override still allowed.
        is_contract_mode = env != "production" and os.getenv("DENIS_CONTRACT_TEST_MODE") == "1"

        # Additional safety: never activate via headers/query params in production
        if env == "production":
            is_contract_mode = False

        if is_contract_mode:
            # Return deterministic response for contract testing
            return self._generate_deterministic_response(req)

        handler = _ChatHandler(self.flags)
        return await handler.generate(req)

    def _extract_user_text(self, messages) -> str:
        """Extract user text from messages for deterministic response."""
        for message in reversed(messages):
            if hasattr(message, "role") and hasattr(message, "content"):
                if message.role == "user" and message.content:
                    return str(message.content)
        return "test message"

    def _generate_deterministic_response(self, req: ChatCompletionRequest) -> dict[str, Any]:
        """Generate deterministic response for contract testing."""
        completion_id = "chatcmpl-deterministic-test"
        user_text = self._extract_user_text(req.messages) if req.messages else "test message"
        prompt_tokens = max(1, len(user_text.split()))

        # Deterministic content based on request
        if "tool" in user_text.lower():
            # Tool call scenario
            tool_call = {
                "id": "call_deterministic_test",
                "type": "function",
                "function": {"name": "test_tool", "arguments": '{"action": "test"}'},
            }
            content = None
            finish_reason = "tool_calls"
            tool_calls = [tool_call]
        else:
            # Normal response scenario
            content = "Deterministic test response for contract validation."
            finish_reason = "stop"
            tool_calls = None

        completion_tokens = max(1, len((content or "").split()))

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": 1234567890,  # Fixed timestamp
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "meta": {"path": "deterministic_test"},
        }


def build_openai_router(runtime: DenisRuntime) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["openai"])
    logger = logging.getLogger("denis.chat")

    @router.get("/models")
    async def list_models() -> dict[str, Any]:
        try:
            return {"object": "list", "data": runtime.models}
        except Exception:
            # Fail-open degraded response
            return {
                "object": "list",
                "data": [{"id": "denis-cognitive", "object": "model"}],
            }

    @router.post("/chat/completions")
    async def chat_completions(req: ChatCompletionRequest, request: Request):
        ip = request.client.host if request.client else "unknown"
        user = ip
        # Event bus identifiers (fail-open; do not persist raw prompts).
        conv_id = (
            (request.headers.get("x-denis-conversation-id") or "").strip()
            or (request.query_params.get("conversation_id") or "").strip()
            or "default"
        )
        trace_id = (request.headers.get("x-denis-trace-id") or "").strip() or str(uuid.uuid4())

        # Best-effort: materialize selected event_v1 into Graph (SSoT). Must never break /chat.
        def _materialize_event(ev: dict[str, Any] | None) -> None:
            if not isinstance(ev, dict):
                return
            try:
                from denis_unified_v1.graph.materializers.event_materializer import (
                    maybe_materialize_event,
                )

                maybe_materialize_event(ev)
            except Exception:
                return

        # Extract user text once for safe hashing + RAG.
        user_text_for_hash = ""
        try:
            for msg in reversed(req.messages or []):
                if msg.role == "user" and isinstance(msg.content, str):
                    user_text_for_hash = msg.content
                    break
        except Exception:
            user_text_for_hash = ""

        # WS10-G: Graph-first Intent/Plan/Tasks (fail-open, never blocks chat).
        # WS15/WS10-G: align graph turn_id with persona/event trace_id for correlation.
        turn_id = (trace_id or "").strip() or str(uuid.uuid4())
        ws10g_result: dict[str, Any] = {"success": False, "warning": None}
        try:
            from denis_unified_v1.graph.graph_intent_plan import create_intent_plan_tasks

            ws10g_result = create_intent_plan_tasks(
                conversation_id=conv_id,
                turn_id=turn_id,
                user_text=user_text_for_hash,
                modality="text",
            )
        except Exception:
            pass  # fail-open: never block chat

        # Emit WS events for timeline (mirrors graph state).
        if ws10g_result.get("success"):
            try:
                from api.persona.event_router import persona_emit as emit_event

                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="plan.created",
                    severity="info",
                    ui_hint={"render": "plan_created", "icon": "checklist"},
                    payload={
                        "intent_id": ws10g_result.get("intent_id"),
                        "plan_id": ws10g_result.get("plan_id"),
                        "task_count": len(ws10g_result.get("task_ids", [])),
                    },
                )
                for task_id in ws10g_result.get("task_ids", []):
                    emit_event(
                        conversation_id=conv_id,
                        trace_id=trace_id,
                        type="plan.task.created",
                        severity="info",
                        ui_hint={"render": "task_created", "icon": "task"},
                        payload={
                            "task_id": task_id,
                            "plan_id": ws10g_result.get("plan_id"),
                        },
                    )
            except Exception:
                pass  # fail-open

        # RAG (fail-open; optional). Emits WS events, can optionally inject a system context block.
        rag_chunk_ids: list[str] = []
        try:
            rag_enabled = (os.getenv("RAG_ENABLED") or "").strip().lower() in {
                "1",
                "true",
                "yes",
            }
            if not rag_enabled:
                raise RuntimeError("rag_disabled")

            from api.persona.event_router import persona_emit as emit_event
            from api.telemetry_store import sha256_text
            from denis_unified_v1.rag.context_builder import build_rag_context_pack

            rag_pack = build_rag_context_pack(
                user_text=user_text_for_hash, trace_id=trace_id, conversation_id=conv_id
            )
            if rag_pack.query:
                k = int(os.getenv("RAG_TOPK", "8"))
                ev = emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="rag.search.start",
                    severity="info",
                    ui_hint={
                        "render": "rag_search",
                        "icon": "search",
                        "collapsible": True,
                    },
                    payload={
                        "query_sha256": sha256_text(rag_pack.query),
                        "query_len": len(rag_pack.query or ""),
                        "k": k,
                        "filters": {"kind": os.getenv("RAG_KIND_FILTER") or None},
                    },
                )
                _materialize_event(ev)

                rag_chunk_ids = [
                    c.get("chunk_id")
                    for c in (rag_pack.chunks or [])
                    if isinstance(c, dict) and c.get("chunk_id")
                ]

                ev = emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="rag.search.result",
                    severity="info",
                    ui_hint={"render": "rag_results", "icon": "list", "collapsible": True},
                    payload={
                        "selected": [
                            {
                                "chunk_id": c.get("chunk_id"),
                                "score": c.get("score"),
                                "source": (c.get("provenance") or {}).get("source")
                                if isinstance(c.get("provenance"), dict)
                                else None,
                                "hash_sha256": (c.get("provenance") or {}).get("hash_sha256")
                                if isinstance(c.get("provenance"), dict)
                                else None,
                            }
                            for c in (rag_pack.chunks or [])
                            if isinstance(c, dict)
                        ],
                        "warning": rag_pack.warning,
                    },
                )
                _materialize_event(ev)

                ev = emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="rag.context.compiled",
                    severity="info",
                    ui_hint={"render": "rag_context", "icon": "stack", "collapsible": True},
                    payload={
                        "chunks_count": int(len(rag_pack.chunks or [])),
                        "citations": list(rag_pack.citations or []),
                    },
                )
                _materialize_event(ev)

                if (os.getenv("RAG_INJECT") or "").strip().lower() in {"1", "true", "yes"}:
                    # Safe system block (redacted snippets only).
                    lines = ["RAG_CONTEXT (redacted snippets):"]
                    for c in (rag_pack.chunks or [])[:8]:
                        if not isinstance(c, dict):
                            continue
                        snippet = (c.get("snippet_redacted") or "").strip()
                        cid = c.get("chunk_id")
                        if cid and snippet:
                            lines.append(f"- [{cid}] {snippet}")
                    context_msg = "\n".join(lines)[:4000]  # hard cap
                    try:
                        req.messages.insert(0, ChatMessage(role="system", content=context_msg))
                    except Exception:
                        pass
        except Exception:
            rag_chunk_ids = []

        # Anti-loop protection: if Denis calls an endpoint that points back to Denis,
        # the request will re-enter with X-Denis-Hop already set. Default policy:
        # reject any re-entry (hop > 0) with a fail-soft degraded response.
        hop = parse_hop(request.headers.get("x-denis-hop"))
        try:
            max_hop = int(os.getenv("DENIS_OPENAI_COMPAT_MAX_HOP", "0"))
        except Exception:
            max_hop = 0

        try:
            if hop > max_hop:
                # Emit minimal events (blocked).
                try:
                    from api.telemetry_store import sha256_text
                    from api.persona.event_router import persona_emit as emit_event

                    user_text = ""
                    for msg in reversed(req.messages or []):
                        if msg.role == "user" and isinstance(msg.content, str):
                            user_text = msg.content
                            break
                    emit_event(
                        conversation_id=conv_id,
                        trace_id=trace_id,
                        type="chat.message",
                        severity="info",
                        ui_hint={"render": "chat_bubble", "icon": "message"},
                        payload={
                            "role": "user",
                            "content_sha256": sha256_text(user_text),
                            "content_len": len(user_text or ""),
                        },
                    )
                    emit_event(
                        conversation_id=conv_id,
                        trace_id=trace_id,
                        type="agent.reasoning.summary",
                        severity="warning",
                        ui_hint={
                            "render": "reasoning_summary",
                            "icon": "brain",
                            "collapsible": True,
                        },
                        payload={
                            "adaptive_reasoning": {
                                "goal_sha256": sha256_text(user_text),
                                "goal_len": len(user_text or ""),
                                "constraints_hit": ["anti_loop_x_denis_hop"],
                                "tools_used": [],
                                "retrieval": {"chunk_ids": rag_chunk_ids},
                                "next_action": None,
                            }
                        },
                    )
                    ev = emit_event(
                        conversation_id=conv_id,
                        trace_id=trace_id,
                        type="agent.decision_trace_summary",
                        severity="warning",
                        ui_hint={"render": "decision_trace", "icon": "route"},
                        payload={"blocked": True, "x_denis_hop": hop, "path": "blocked_hop"},
                    )
                    _materialize_event(ev)
                except Exception:
                    pass
                try:
                    from api.telemetry_store import get_telemetry_store, sha256_text

                    user_text = ""
                    for msg in reversed(req.messages or []):
                        if msg.role == "user" and isinstance(msg.content, str):
                            user_text = msg.content
                            break
                    get_telemetry_store().record_chat_decision(
                        {
                            "request_id": None,
                            "model": req.model,
                            "x_denis_hop": hop,
                            "blocked": True,
                            "path": "blocked_hop",
                            "prompt_sha256": sha256_text(user_text),
                            "prompt_chars": len(user_text or ""),
                        }
                    )
                except Exception:
                    pass
                try:
                    logger.warning(
                        "chat_blocked_hop hop=%s max_hop=%s model=%s",
                        hop,
                        max_hop,
                        req.model,
                    )
                except Exception:
                    pass
                return JSONResponse(
                    status_code=200,
                    content={
                        "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
                        "object": "chat.completion",
                        "created": _utc_now(),
                        "model": req.model,
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": "Degraded response: loop protection (X-Denis-Hop) blocked request.",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                        "meta": {
                            "path": "blocked_hop",
                            "x_denis_hop": hop,
                            "max_hop": max_hop,
                        },
                    },
                )

            # Emit user message event (redacted) on accept.
            try:
                from api.telemetry_store import sha256_text
                from api.persona.event_router import persona_emit as emit_event

                user_text = ""
                for msg in reversed(req.messages or []):
                    if msg.role == "user" and isinstance(msg.content, str):
                        user_text = msg.content
                        break
                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="chat.message",
                    severity="info",
                    ui_hint={"render": "chat_bubble", "icon": "message"},
                    payload={
                        "role": "user",
                        "content_sha256": sha256_text(user_text),
                        "content_len": len(user_text or ""),
                    },
                )
                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="run.step",
                    severity="info",
                    ui_hint={"render": "step", "icon": "list", "collapsible": True},
                    payload={"step_id": "chat_completions", "state": "RUNNING"},
                )
            except Exception:
                pass

            if req.stream:
                completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
                created = _utc_now()

                async def event_stream():
                    # Start chunk: declare assistant role early.
                    yield sse_event(
                        _openai_chunk(
                            completion_id=completion_id,
                            created=created,
                            model=req.model,
                            delta={"role": "assistant"},
                            finish_reason=None,
                        )
                    )

                    try:
                        hop_token = set_current_hop(hop)
                        try:
                            result = await runtime.generate(req)
                        finally:
                            reset_hop(hop_token)

                        # Best-effort telemetry + WS events (redacted). Keep same semantics as non-streaming.
                        try:
                            from api.telemetry_store import get_telemetry_store, sha256_text

                            meta = (result or {}).get("meta") if isinstance(result, dict) else {}
                            router_meta = (
                                (meta or {}).get("router") if isinstance(meta, dict) else {}
                            )
                            get_telemetry_store().record_chat_decision(
                                {
                                    "request_id": completion_id,
                                    "model": req.model,
                                    "x_denis_hop": hop,
                                    "blocked": False,
                                    "path": (meta or {}).get("path")
                                    if isinstance(meta, dict)
                                    else None,
                                    "llm_used": router_meta.get("llm_used")
                                    if isinstance(router_meta, dict)
                                    else None,
                                    "engine_id": router_meta.get("engine_id")
                                    if isinstance(router_meta, dict)
                                    else None,
                                    "latency_ms": router_meta.get("latency_ms")
                                    if isinstance(router_meta, dict)
                                    else None,
                                    "prompt_sha256": sha256_text(user_text_for_hash),
                                    "prompt_chars": len(user_text_for_hash or ""),
                                }
                            )
                        except Exception:
                            pass

                        # Emit decision trace summary + assistant message + latency metric (all redacted).
                        try:
                            from api.persona.event_router import persona_emit as emit_event
                            from api.telemetry_store import sha256_text

                            meta = result.get("meta") if isinstance(result, dict) else {}
                            router_meta = (
                                (meta or {}).get("router") if isinstance(meta, dict) else {}
                            )

                            assistant_text_for_hash = ""
                            try:
                                assistant_text_for_hash = (
                                    (result.get("choices") or [{}])[0]
                                    .get("message", {})
                                    .get("content")
                                ) or ""
                            except Exception:
                                assistant_text_for_hash = ""

                            adaptive_reasoning = {
                                "goal_sha256": sha256_text(user_text_for_hash),
                                "goal_len": len(user_text_for_hash or ""),
                                "constraints_hit": [],
                                "tools_used": [],
                                "retrieval": {"chunk_ids": rag_chunk_ids},
                                "why_picked": "router_meta" if router_meta else "degraded_or_local",
                                "next_action": None,
                            }
                            emit_event(
                                conversation_id=conv_id,
                                trace_id=trace_id,
                                type="agent.reasoning.summary",
                                severity="info",
                                ui_hint={
                                    "render": "reasoning_summary",
                                    "icon": "brain",
                                    "collapsible": True,
                                },
                                payload={"adaptive_reasoning": adaptive_reasoning},
                            )
                            ev = emit_event(
                                conversation_id=conv_id,
                                trace_id=trace_id,
                                type="agent.decision_trace_summary",
                                severity="info",
                                ui_hint={"render": "decision_trace", "icon": "route"},
                                payload={
                                    "blocked": False,
                                    "x_denis_hop": hop,
                                    "path": (meta or {}).get("path")
                                    if isinstance(meta, dict)
                                    else None,
                                    "engine_id": router_meta.get("engine_id")
                                    if isinstance(router_meta, dict)
                                    else None,
                                    "llm_used": router_meta.get("llm_used")
                                    if isinstance(router_meta, dict)
                                    else None,
                                    "latency_ms": router_meta.get("latency_ms")
                                    if isinstance(router_meta, dict)
                                    else None,
                                },
                            )
                            _materialize_event(ev)

                            emit_event(
                                conversation_id=conv_id,
                                trace_id=trace_id,
                                type="chat.message",
                                severity="info",
                                ui_hint={"render": "chat_bubble", "icon": "message"},
                                payload={
                                    "role": "assistant",
                                    "content_sha256": sha256_text(assistant_text_for_hash),
                                    "content_len": len(assistant_text_for_hash or ""),
                                },
                            )

                            emit_event(
                                conversation_id=conv_id,
                                trace_id=trace_id,
                                type="run.step",
                                severity="info",
                                ui_hint={
                                    "render": "step",
                                    "icon": "list",
                                    "collapsible": True,
                                },
                                payload={"step_id": "chat_completions", "state": "SUCCESS"},
                            )
                        except Exception:
                            pass

                        assistant_text = ""
                        tool_calls: list[dict[str, Any]] | None = None
                        finish_reason = "stop"
                        try:
                            choices = (
                                result.get("choices") if isinstance(result, dict) else None
                            )
                            choice0 = (choices or [{}])[0] if isinstance(choices, list) else {}
                            msg0 = (
                                (choice0.get("message") or {})
                                if isinstance(choice0, dict)
                                else {}
                            )
                            assistant_text = str(msg0.get("content") or "")
                            tc = msg0.get("tool_calls")
                            if isinstance(tc, list) and tc:
                                tool_calls = tc
                                finish_reason = "tool_calls"
                        except Exception:
                            assistant_text = ""
                            tool_calls = None
                            finish_reason = "stop"

                        if tool_calls:
                            yield sse_event(
                                _openai_chunk(
                                    completion_id=completion_id,
                                    created=created,
                                    model=req.model,
                                    delta={"tool_calls": tool_calls},
                                    finish_reason=None,
                                )
                            )
                            yield sse_event(
                                _openai_chunk(
                                    completion_id=completion_id,
                                    created=created,
                                    model=req.model,
                                    delta={},
                                    finish_reason="tool_calls",
                                )
                            )
                            yield "data: [DONE]\n\n"
                            return

                        for chunk in _iter_text_chunks(assistant_text, chunk_chars=64):
                            if not chunk:
                                continue
                            yield sse_event(
                                _openai_chunk(
                                    completion_id=completion_id,
                                    created=created,
                                    model=req.model,
                                    delta={"content": chunk},
                                    finish_reason=None,
                                )
                            )

                        yield sse_event(
                            _openai_chunk(
                                completion_id=completion_id,
                                created=created,
                                model=req.model,
                                delta={},
                                finish_reason=finish_reason,
                            )
                        )
                        yield "data: [DONE]\n\n"
                    except Exception as e:
                        # Fail-open: convert stream failure to a small degraded stream.
                        degraded = f"Degraded response: {type(e).__name__}: {str(e)[:200]}"
                        for chunk in _iter_text_chunks(degraded, chunk_chars=64):
                            yield sse_event(
                                _openai_chunk(
                                    completion_id=completion_id,
                                    created=created,
                                    model=req.model,
                                    delta={"content": chunk},
                                    finish_reason=None,
                                )
                            )
                        yield sse_event(
                            _openai_chunk(
                                completion_id=completion_id,
                                created=created,
                                model=req.model,
                                delta={},
                                finish_reason="stop",
                            )
                        )
                        yield "data: [DONE]\n\n"

                return StreamingResponse(
                    event_stream(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache"},
                )

            hop_token = set_current_hop(hop)
            try:
                result = await runtime.generate(req)
            finally:
                reset_hop(hop_token)
            try:
                from api.telemetry_store import get_telemetry_store, sha256_text

                user_text = ""
                for msg in reversed(req.messages or []):
                    if msg.role == "user" and isinstance(msg.content, str):
                        user_text = msg.content
                        break
                meta = (result or {}).get("meta") if isinstance(result, dict) else {}
                router_meta = (meta or {}).get("router") if isinstance(meta, dict) else {}
                get_telemetry_store().record_chat_decision(
                    {
                        "request_id": (result or {}).get("id")
                        if isinstance(result, dict)
                        else None,
                        "model": req.model,
                        "x_denis_hop": hop,
                        "blocked": False,
                        "path": (meta or {}).get("path") if isinstance(meta, dict) else None,
                        "llm_used": router_meta.get("llm_used")
                        if isinstance(router_meta, dict)
                        else None,
                        "engine_id": router_meta.get("engine_id")
                        if isinstance(router_meta, dict)
                        else None,
                        "latency_ms": router_meta.get("latency_ms")
                        if isinstance(router_meta, dict)
                        else None,
                        "prompt_sha256": sha256_text(user_text),
                        "prompt_chars": len(user_text or ""),
                    }
                )
            except Exception:
                pass

            # Emit decision trace summary + assistant message + latency metric (all redacted).
            try:
                from api.persona.event_router import persona_emit as emit_event
                from api.telemetry_store import sha256_text

                meta = result.get("meta") if isinstance(result, dict) else {}
                router_meta = (meta or {}).get("router") if isinstance(meta, dict) else {}

                assistant_text = ""
                try:
                    assistant_text = (
                        (result.get("choices") or [{}])[0]
                        .get("message", {})
                        .get("content")
                    ) or ""
                except Exception:
                    assistant_text = ""

                adaptive_reasoning = {
                    "goal_sha256": sha256_text(user_text_for_hash),
                    "goal_len": len(user_text_for_hash or ""),
                    "constraints_hit": [],
                    "tools_used": [],
                    "retrieval": {"chunk_ids": rag_chunk_ids},
                    "why_picked": "router_meta" if router_meta else "degraded_or_local",
                    "next_action": None,
                }
                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="agent.reasoning.summary",
                    severity="info",
                    ui_hint={"render": "reasoning_summary", "icon": "brain", "collapsible": True},
                    payload={"adaptive_reasoning": adaptive_reasoning},
                )
                ev = emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="agent.decision_trace_summary",
                    severity="info",
                    ui_hint={"render": "decision_trace", "icon": "route"},
                    payload={
                        "blocked": False,
                        "x_denis_hop": hop,
                        "path": (meta or {}).get("path") if isinstance(meta, dict) else None,
                        "engine_id": router_meta.get("engine_id")
                        if isinstance(router_meta, dict)
                        else None,
                        "llm_used": router_meta.get("llm_used") if isinstance(router_meta, dict) else None,
                        "latency_ms": router_meta.get("latency_ms")
                        if isinstance(router_meta, dict)
                        else None,
                    },
                )
                _materialize_event(ev)

                # Link to DecisionTrace (Graph SSoT) with safe summary only (fail-open).
                try:
                    from denis_unified_v1.actions.decision_trace import emit_decision_trace

                    emit_decision_trace(
                        kind="policy_eval",
                        mode="PASSED",
                        reason="adaptive_reasoning_record",
                        request_id=(result.get("id") if isinstance(result, dict) else None),
                        extra={"adaptive_reasoning": adaptive_reasoning},
                    )
                except Exception:
                    pass

                # Auto-index safe record (optional; fail-open).
                try:
                    indexing_enabled = (os.getenv("INDEXING_ENABLED") or "").strip().lower() in {
                        "1",
                        "true",
                        "yes",
                    }
                    if indexing_enabled:
                        from denis_unified_v1.indexing.indexing_bus import (
                            get_indexing_bus,
                            IndexPiece,
                        )

                        bus = get_indexing_bus()
                        idx_status = bus.upsert_piece(
                            IndexPiece(
                                kind="decision_summary",
                                title="Adaptive reasoning record",
                                content=str(adaptive_reasoning),
                                tags=["adaptive_reasoning"],
                                source="agent",
                                trace_id=trace_id,
                                conversation_id=conv_id,
                                provider=router_meta.get("llm_used")
                                if isinstance(router_meta, dict)
                                else None,
                                extra={
                                    "request_id": (
                                        result.get("id") if isinstance(result, dict) else None
                                    )
                                },
                            )
                        )
                        if isinstance(idx_status, dict) and idx_status.get("hash_sha256"):
                            emit_event(
                                conversation_id=conv_id,
                                trace_id=trace_id,
                                type="indexing.upsert",
                                severity="info",
                                ui_hint={
                                    "render": "indexing",
                                    "icon": "database",
                                    "collapsible": True,
                                },
                                payload={
                                    "kind": "decision_summary",
                                    "hash_sha256": idx_status.get("hash_sha256"),
                                    "status": idx_status.get("status"),
                                },
                            )
                except Exception:
                    pass

                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="chat.message",
                    severity="info",
                    ui_hint={"render": "chat_bubble", "icon": "message"},
                    payload={
                        "role": "assistant",
                        "content_sha256": sha256_text(assistant_text),
                        "content_len": len(assistant_text or ""),
                    },
                )
                latency_ms = (
                    router_meta.get("latency_ms") if isinstance(router_meta, dict) else None
                )
                if latency_ms is not None:
                    emit_event(
                        conversation_id=conv_id,
                        trace_id=trace_id,
                        type="ops.metric",
                        severity="info",
                        ui_hint={"render": "metric", "icon": "gauge", "collapsible": True},
                        payload={
                            "name": "chat.latency_ms",
                            "value": float(latency_ms),
                            "unit": "ms",
                            "labels": {"endpoint": "/v1/chat/completions"},
                        },
                    )
                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="run.step",
                    severity="info",
                    ui_hint={"render": "step", "icon": "list", "collapsible": True},
                    payload={"step_id": "chat_completions", "state": "SUCCESS"},
                )
            except Exception:
                pass
            try:
                meta = result.get("meta") if isinstance(result, dict) else {}
                logger.info(
                    "chat_ok model=%s hop=%s path=%s",
                    req.model,
                    hop,
                    (meta or {}).get("path") if isinstance(meta, dict) else None,
                )
            except Exception:
                pass
            return JSONResponse(status_code=200, content=result)
        except Exception as e:
            # Fail-open degraded response
            try:
                logger.exception("chat_failed model=%s hop=%s", req.model, hop)
            except Exception:
                pass

            degraded_content = f"Degraded response: {str(e)}"
            try:
                from api.persona.event_router import persona_emit as emit_event
                from api.telemetry_store import sha256_text

                adaptive_reasoning = {
                    "goal_sha256": sha256_text(user_text_for_hash),
                    "goal_len": len(user_text_for_hash or ""),
                    "constraints_hit": ["degraded"],
                    "tools_used": [],
                    "retrieval": {"chunk_ids": rag_chunk_ids},
                    "why_picked": "degraded_exception",
                    "next_action": None,
                }
                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="agent.reasoning.summary",
                    severity="warning",
                    ui_hint={"render": "reasoning_summary", "icon": "brain", "collapsible": True},
                    payload={"adaptive_reasoning": adaptive_reasoning},
                )
                ev = emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="agent.decision_trace_summary",
                    severity="warning",
                    ui_hint={"render": "decision_trace", "icon": "route"},
                    payload={
                        "blocked": False,
                        "x_denis_hop": hop,
                        "path": "degraded",
                        "engine_id": None,
                        "llm_used": None,
                        "latency_ms": None,
                    },
                )
                _materialize_event(ev)

                # Optional: link to DecisionTrace (Graph SSoT), fail-open.
                try:
                    from denis_unified_v1.actions.decision_trace import emit_decision_trace

                    emit_decision_trace(
                        kind="policy_eval",
                        mode="SKIPPED",
                        reason="adaptive_reasoning_record_degraded",
                        request_id=None,
                        extra={
                            "adaptive_reasoning": adaptive_reasoning,
                            "error": type(e).__name__,
                        },
                    )
                except Exception:
                    pass

                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="chat.message",
                    severity="info",
                    ui_hint={"render": "chat_bubble", "icon": "message"},
                    payload={
                        "role": "assistant",
                        "content_sha256": sha256_text(degraded_content),
                        "content_len": len(degraded_content),
                    },
                )
                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="run.step",
                    severity="warning",
                    ui_hint={"render": "step", "icon": "list", "collapsible": True},
                    payload={"step_id": "chat_completions", "state": "FAILED"},
                )
                ev = emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="error",
                    severity="warning",
                    ui_hint={"render": "error", "icon": "alert", "collapsible": True},
                    payload={"code": "chat_failed", "msg": type(e).__name__},
                )
                _materialize_event(ev)
            except Exception:
                pass
            return JSONResponse(
                status_code=200,
                content={
                    "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
                    "object": "chat.completion",
                    "created": _utc_now(),
                    "model": req.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": degraded_content,
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )
        finally:
            # WS23-G: Neuro WAKE + UPDATE (fail-open, never blocks chat).
            try:
                from denis_unified_v1.feature_flags import load_feature_flags as _load_ff
                _ff = _load_ff()
                if getattr(_ff, "neuro_enabled", True):
                    from denis_unified_v1.neuro.sequences import (
                        wake_sequence,
                        update_sequence,
                        _read_consciousness,
                    )
                    from denis_unified_v1.graph.graph_client import get_graph_client
                    from api.persona.event_router import persona_emit as _neuro_emit

                    _neuro_graph = get_graph_client()

                    # First turn detection: if no ConsciousnessState exists,
                    # run WAKE_SEQUENCE to bootstrap 12 layers.
                    _existing_cs = _read_consciousness(_neuro_graph)
                    if _existing_cs is None:
                        wake_sequence(
                            emit_fn=_neuro_emit,
                            conversation_id=conv_id,
                            graph=_neuro_graph,
                        )

                    _neuro_turn_meta = {
                        "input_sha256": sha256_text(user_text_for_hash)
                        if "sha256_text" in dir()
                        else "",
                        "input_len": len(user_text_for_hash or ""),
                        "modality": "text",
                        "retrieval_count": len(rag_chunk_ids),
                        "chunk_ids_count": len(rag_chunk_ids),
                        "turns_in_session": 1,
                        "errors_count": 0,
                    }
                    update_sequence(
                        emit_fn=_neuro_emit,
                        conversation_id=conv_id,
                        turn_meta=_neuro_turn_meta,
                        graph=_neuro_graph,
                    )
            except Exception:
                pass  # fail-open

    @router.websocket("/chat/completions/ws")
    async def chat_completions_ws(websocket: WebSocket):
        """
        WebSocket streaming endpoint (non-OpenAI standard).

        Protocol:
        - Client sends a ChatCompletionRequest JSON payload.
        - Server streams OpenAI chunk objects as JSON frames.
        - Server ends each completion with {"type":"done","id":...}.
        """
        await websocket.accept()
        try:
            while True:
                payload = await websocket.receive_json()
                try:
                    ws_req = ChatCompletionRequest(**(payload or {}))
                except Exception:
                    await websocket.send_json({"error": "bad_request"})
                    continue

                completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
                created = _utc_now()
                model = ws_req.model

                # Start chunk
                await websocket.send_json(
                    _openai_chunk(
                        completion_id=completion_id,
                        created=created,
                        model=model,
                        delta={"role": "assistant"},
                        finish_reason=None,
                    )
                )

                hop = parse_hop(websocket.headers.get("x-denis-hop"))
                try:
                    max_hop = int(os.getenv("DENIS_OPENAI_COMPAT_MAX_HOP", "0"))
                except Exception:
                    max_hop = 0

                if hop > max_hop:
                    text = "Degraded response: loop protection (X-Denis-Hop) blocked request."
                    for chunk in _iter_text_chunks(text, chunk_chars=64):
                        await websocket.send_json(
                            _openai_chunk(
                                completion_id=completion_id,
                                created=created,
                                model=model,
                                delta={"content": chunk},
                                finish_reason=None,
                            )
                        )
                    await websocket.send_json(
                        _openai_chunk(
                            completion_id=completion_id,
                            created=created,
                            model=model,
                            delta={},
                            finish_reason="stop",
                        )
                    )
                    await websocket.send_json({"type": "done", "id": completion_id})
                    continue

                hop_token = set_current_hop(hop)
                try:
                    result = await runtime.generate(ws_req)
                finally:
                    reset_hop(hop_token)

                assistant_text = ""
                tool_calls: list[dict[str, Any]] | None = None
                finish_reason = "stop"
                try:
                    choices = (
                        result.get("choices") if isinstance(result, dict) else None
                    )
                    choice0 = (choices or [{}])[0] if isinstance(choices, list) else {}
                    msg0 = (
                        (choice0.get("message") or {}) if isinstance(choice0, dict) else {}
                    )
                    assistant_text = str(msg0.get("content") or "")
                    tc = msg0.get("tool_calls")
                    if isinstance(tc, list) and tc:
                        tool_calls = tc
                        finish_reason = "tool_calls"
                except Exception:
                    assistant_text = ""
                    tool_calls = None
                    finish_reason = "stop"

                if tool_calls:
                    await websocket.send_json(
                        _openai_chunk(
                            completion_id=completion_id,
                            created=created,
                            model=model,
                            delta={"tool_calls": tool_calls},
                            finish_reason=None,
                        )
                    )
                    await websocket.send_json(
                        _openai_chunk(
                            completion_id=completion_id,
                            created=created,
                            model=model,
                            delta={},
                            finish_reason="tool_calls",
                        )
                    )
                    await websocket.send_json({"type": "done", "id": completion_id})
                    continue

                for chunk in _iter_text_chunks(assistant_text, chunk_chars=64):
                    if not chunk:
                        continue
                    await websocket.send_json(
                        _openai_chunk(
                            completion_id=completion_id,
                            created=created,
                            model=model,
                            delta={"content": chunk},
                            finish_reason=None,
                        )
                    )

                await websocket.send_json(
                    _openai_chunk(
                        completion_id=completion_id,
                        created=created,
                        model=model,
                        delta={},
                        finish_reason=finish_reason,
                    )
                )
                await websocket.send_json({"type": "done", "id": completion_id})
        except WebSocketDisconnect:
            return
        except Exception:
            return

    return router
