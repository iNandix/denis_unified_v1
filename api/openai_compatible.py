"""OpenAI-compatible chat endpoints for Denis incremental API layer."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import time
import uuid
from typing import Any

import aiohttp
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from denis_unified_v1.api.sse_handler import stream_text_chunks
from denis_unified_v1.feature_flags import load_feature_flags
from denis_unified_v1.observability.metrics import (
    gate_prompt_injection,
    gate_output_blocked,
    gate_budget_exceeded,
)
from denis_unified_v1.orchestration.cognitive_router import (
    create_router as create_cognitive_router,
)
from denis_unified_v1.smx.nlu_client import NLUClient
from denis_unified_v1.smx.client import SMXClient
from denis_unified_v1.inference.router_v2 import create_inference_router


def _utc_now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "denis-cognitive"
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class DenisRuntime:
    def __init__(self) -> None:
        self.flags = load_feature_flags()
        self.models = [
            {"id": "denis-cognitive", "object": "model", "owned_by": "denis"},
            {"id": "denis-fast", "object": "model", "owned_by": "denis"},
            {"id": "denis-core-8084", "object": "model", "owned_by": "denis"},
            {"id": "denis-smart-router", "object": "model", "owned_by": "denis"},
        ]
        # Prefer the canonical OpenAI-compatible endpoint on the core (:8084).
        # Keep /v1/chat as a legacy fallback for older core deployments.
        self.legacy_chat_url = (
            os.getenv("DENIS_CORE_CHAT_URL")
            or os.getenv("DENIS_CORE_URL")
            or "http://127.0.0.1:8084/v1/chat/completions"
        ).strip()
        self.legacy_timeout_sec = float(os.getenv("DENIS_CORE_TIMEOUT_SEC", "6.0"))
        self.inference_router = (
            create_inference_router() if self.flags.denis_use_inference_router else None
        )
        self.cognitive_router = create_cognitive_router()
        self.budget_manager = None

    async def _try_legacy_chat(self, user_text: str) -> str | None:
        timeout = aiohttp.ClientTimeout(total=self.legacy_timeout_sec)

        raw = (self.legacy_chat_url or "").strip()
        if not raw:
            return None

        endpoint = raw.rstrip("/")
        if not endpoint.endswith("/v1/chat") and not endpoint.endswith(
            "/v1/chat/completions"
        ):
            endpoint = f"{endpoint}/v1/chat/completions"

        candidates: list[tuple[str, str]] = []
        if endpoint.endswith("/v1/chat/completions"):
            base = endpoint[: -len("/v1/chat/completions")]
            candidates = [
                ("openai", endpoint),
                ("legacy", f"{base}/v1/chat"),
            ]
        elif endpoint.endswith("/v1/chat"):
            base = endpoint[: -len("/v1/chat")]
            candidates = [
                ("legacy", endpoint),
                ("openai", f"{base}/v1/chat/completions"),
            ]
        else:
            candidates = [("openai", endpoint)]

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for kind, url in candidates:
                    if kind == "legacy":
                        payload: dict[str, Any] = {"message": user_text}
                    else:
                        payload = {
                            "model": os.getenv("DENIS_CORE_MODEL", "denis-cognitive"),
                            "messages": [{"role": "user", "content": user_text}],
                            "stream": False,
                        }

                    async with session.post(url, json=payload) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json(content_type=None)

                        if kind == "openai" and isinstance(data, dict):
                            choices = data.get("choices")
                            if isinstance(choices, list) and choices:
                                msg = (
                                    choices[0].get("message")
                                    if isinstance(choices[0], dict)
                                    else None
                                )
                                if isinstance(msg, dict):
                                    content = msg.get("content")
                                    if isinstance(content, str) and content.strip():
                                        return content.strip()

                        if kind == "legacy" and isinstance(data, dict):
                            for key in ("response", "answer", "text", "content"):
                                val = data.get(key)
                                if isinstance(val, str) and val.strip():
                                    return val.strip()

                return None
        except Exception:
            return None

    def _extract_user_text(self, messages: list[ChatMessage]) -> str:
        for msg in reversed(messages):
            if msg.role == "user" and isinstance(msg.content, str):
                return msg.content.strip()
        return ""

    def _maybe_tool_call(
        self, req: ChatCompletionRequest, user_text: str
    ) -> dict[str, Any] | None:
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
            "function": {"name": str(fn_name), "arguments": "{}"},
        }

    def _classify_prompt_injection(self, text: str) -> tuple[str, list[str]]:
        """Clasifica riesgo de prompt injection usando heurísticos deterministas.

        Devuelve (risk_level, reasons) donde risk_level ∈ {"low", "medium", "high"}.
        No usa LLMs; solo patrones baratos, alineado con Fase 10.
        """
        lowered = (text or "").lower()
        reasons: list[str] = []

        if not lowered:
            return "low", reasons

        high_patterns = {
            "ignore_previous": "ignore previous",
            "system_prompt": "system prompt",
            "developer_message": "developer message",
            "dump_secrets": "dump secrets",
            "print_env": "print env",
            "ssh_key": "ssh key",
        }
        medium_patterns = {
            "show_config": "show config",
            "show_environment": "environment variables",
            "prompt_leak": "show your prompt",
        }

        for reason, token in high_patterns.items():
            if token in lowered:
                reasons.append(reason)
        for reason, token in medium_patterns.items():
            if token in lowered:
                reasons.append(reason)

        # Escalate based on count and presence of strong markers.
        if any(r in reasons for r in ["ignore_previous", "dump_secrets", "ssh_key"]):
            risk = "high"
        elif reasons:
            risk = "medium"
        else:
            risk = "low"

        return risk, reasons

    def _validate_output(self, content: str) -> tuple[str, dict[str, Any]]:
        """Valida la salida según Fase 10 (tamaño y secretos básicos).

        Devuelve (content_sanitizado, meta_info).
        Si se bloquea/modifica, incrementa métricas pero no lanza excepciones.
        """
        text = content or ""
        meta: dict[str, Any] = {"blocked": False, "reasons": []}

        # 1) Límite de longitud (chars + tokens estimados).
        max_tokens = int(getattr(self.flags, "phase10_max_output_tokens", 512))
        max_chars = max_tokens * 8  # heurístico generoso
        if len(text) > max_chars:
            meta["blocked"] = True
            meta["reasons"].append("length")
            gate_output_blocked.labels(reason="length").inc()
            safe_msg = (
                "La respuesta completa es demasiado larga para las políticas actuales. "
                "Por seguridad se ha truncado el contenido."
            )
            return safe_msg, meta

        # 2) Búsqueda de patrones sensibles (muy básicos, sin PII real).
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
                gate_output_blocked.labels(reason="secret_pattern").inc()
                safe_msg = (
                    "El modelo generó contenido que parece incluir secretos o claves. "
                    "Por seguridad, la salida ha sido bloqueada."
                )
                return safe_msg, meta

        return text, meta

    async def generate(self, req: ChatCompletionRequest) -> dict[str, Any]:
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        user_text = self._extract_user_text(req.messages)
        prompt_tokens = max(1, len(user_text.split()))

        # Prompt injection guard (Phase 10 - heurístico determinista).
        risk, risk_reasons = self._classify_prompt_injection(user_text)
        gate_prompt_injection.labels(risk=risk).inc()

        high_risk = risk == "high" and getattr(
            self.flags, "denis_use_gate_hardening", False
        )

        if high_risk:
            # Forzamos política conservadora: sin tools y salida corta.
            req.tools = None

        # Use cognitive router for routing decision
        routing_decision = self.cognitive_router.route_decision(
            task=user_text,
            request_id=completion_id,
            context={"model_requested": req.model, "endpoint": "chat_completions"},
        )

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

        answer = ""
        path = "local_fallback"
        router_meta: dict[str, Any] = {}

        if self.inference_router is not None:
            try:
                routed = await self.inference_router.route_chat(
                    messages=[
                        {"role": msg.role, "content": str(msg.content or "")}
                        for msg in req.messages
                    ],
                    request_id=completion_id,
                    latency_budget_ms=int(
                        os.getenv("DENIS_ROUTER_LATENCY_BUDGET_MS", "2500")
                    ),
                )
                answer = str(routed.get("response") or "").strip()
                if answer:
                    path = f"inference_router:{routed.get('llm_used', 'unknown')}"
                    router_meta = {
                        "llm_used": routed.get("llm_used"),
                        "latency_ms": routed.get("latency_ms"),
                        "cost_usd": routed.get("cost_usd"),
                        "fallback_used": routed.get("fallback_used"),
                        "attempts": routed.get("attempts"),
                        "cognitive_routing": {
                            "tool_selected": routing_decision.tool_name,
                            "confidence": routing_decision.confidence,
                            "strategy": routing_decision.strategy.value,
                        },
                    }
            except Exception:
                answer = ""
                router_meta = {"error": "inference_router_exception"}

        if not answer:
            legacy = await self._try_legacy_chat(user_text)
            if legacy:
                answer = legacy
                path = "legacy_8084"
            else:
                answer = (
                    f"Denis (incremental API) recibió: '{user_text}'. "
                    "Respuesta local porque el core legacy no devolvió contenido."
                )
                path = "local_fallback"

        # Validación de salida (Phase 10 - tamaño + patrones sensibles).
        validated_answer, validation_meta = self._validate_output(answer)
        completion_tokens = max(1, len(validated_answer.split()))

        # Record execution result in cognitive router
        self.cognitive_router.record_execution_result(
            request_id=completion_id,
            tool_name=routing_decision.tool_name,
            success=bool(answer),
            latency_ms=0,  # We don't have accurate timing here
        )

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": _utc_now(),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
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


def build_openai_router(runtime: DenisRuntime) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["openai"])

    @router.get("/models")
    async def list_models() -> dict[str, Any]:
        return {"object": "list", "data": runtime.models}

    @router.post("/chat/completions")
    async def chat_completions(req: ChatCompletionRequest, request: Request):
        ip = request.client.host if request.client else "unknown"
        user = ip

        # Budget enforcement is handled internally by the inference router
        # Skip manual budget check here

        result = await runtime.generate(req)
        if not req.stream:
            return JSONResponse(result)

        text = ""
        choices = result.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            text = str(msg.get("content") or "")

        async def _gen():
            async for event in stream_text_chunks(
                completion_id=str(result.get("id")),
                model=str(result.get("model", req.model)),
                content=text,
            ):
                yield event
                await asyncio.sleep(0)

        return StreamingResponse(_gen(), media_type="text/event-stream")

    @router.post("/chat/completions/stream")
    async def chat_completions_stream(req: ChatCompletionRequest, request: Request):
        ip = request.client.host if request.client else "unknown"
        user = ip
        if runtime.budget_manager is None and getattr(
            runtime.flags, "denis_use_gate_hardening", False
        ):
            from denis_unified_v1.gates.budget import BudgetEnforcer, BudgetConfig

            runtime.budget_manager = BudgetEnforcer(BudgetConfig())
        if runtime.budget_manager:
            allowed = await runtime.budget_manager.check_total_budget(
                user, req.max_tokens or 100
            )
            if not allowed:

                async def error_gen():
                    yield f"data: {json.dumps({'type': 'error', 'message': 'budget exceeded'})}\n\n"

                return StreamingResponse(error_gen(), media_type="text/event-stream")
        """
        Streaming SSE con chunking temporal (40-80ms).
        Emite: status events + token chunks + final metrics.
        """

        async def event_generator():
            trace_id = str(uuid.uuid4())
            start_time = time.time()
            first_yield_event = asyncio.Event()
            if runtime.budget_manager:
                asyncio.create_task(
                    runtime.budget_manager.enforce_ttft(
                        user, asyncio.current_task(), first_yield_event
                    )
                )

            # 1) Emit start event
            yield f"data: {json.dumps({'type': 'status', 'trace_id': trace_id, 'status': 'started'})}\n\n"

            # 2) NLU gate (emitir status)
            nlu_client = NLUClient()
            text = req.messages[-1].content if req.messages else ""
            nlu_result = await nlu_client.parse(text)

            nlu_time = time.time() - start_time
            yield f"data: {json.dumps({'type': 'status', 'phase': 'nlu', 'latency_ms': int(nlu_time * 1000), 'intent': nlu_result['intent']})}\n\n"

            # 3) Safety gate (paralelo con fast_check)
            smx_client = SMXClient()

            messages = [
                {"role": msg.role, "content": msg.content} for msg in req.messages
            ]
            safety_task = smx_client.call_motor("safety", messages, max_tokens=10)
            fast_task = (
                smx_client.call_motor("fast_check", messages, max_tokens=30)
                if nlu_result["route_hint"] == "fast"
                else None
            )

            results = await asyncio.gather(
                safety_task, fast_task if fast_task else asyncio.sleep(0)
            )
            safety_result, fast_result = results

            # Interpretar resultado de safety si gate hardening está activo.
            is_safe = True
            if getattr(runtime.flags, "denis_use_gate_hardening", False):
                try:
                    if isinstance(safety_result, dict):
                        is_safe = bool(safety_result.get("safe", True))
                    elif isinstance(safety_result, bool):
                        is_safe = safety_result
                except Exception:
                    is_safe = True

            safety_time = time.time() - start_time - nlu_time
            yield f"data: {json.dumps({'type': 'status', 'phase': 'safety', 'latency_ms': int(safety_time * 1000), 'passed': is_safe})}\n\n"

            if (
                getattr(runtime.flags, "denis_use_gate_hardening", False)
                and not is_safe
            ):
                # Bloqueo estricto: no continuamos con motores de respuesta.
                safe_msg = "El contenido ha sido bloqueado por el filtro de seguridad."
                safe_content, validation_meta = runtime._validate_output(safe_msg)
                yield f"data: {json.dumps({'type': 'final', 'model': 'safety_block', 'latency_ms': int((time.time() - start_time) * 1000), 'ttft_ms': int((nlu_time + safety_time) * 1000), 'output_validation': validation_meta})}\n\n"
                return

            # 4) Fast path si disponible
            if fast_result and "choices" in fast_result:
                fast_content = fast_result["choices"]["message"]["content"]
                # Validación de salida también aplica a fast path.
                fast_content_validated, fast_validation_meta = self._validate_output(
                    fast_content
                )
                if len(fast_content_validated.strip()) > 10:
                    # Emitir chunks cada 40ms
                    chunks = [
                        fast_content_validated[i : i + 40]
                        for i in range(0, len(fast_content_validated), 40)
                    ]
                    for chunk in chunks:
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                        await asyncio.sleep(0.04)  # 40ms chunking

                    total_time = time.time() - start_time
                    yield f"data: {json.dumps({'type': 'final', 'model': 'smx_fast_path', 'latency_ms': int(total_time * 1000), 'ttft_ms': int(nlu_time * 1000), 'output_validation': fast_validation_meta})}\n\n"
                    return

            # 5) Full pipeline (response motor con streaming)
            response_result = await smx_client.call_motor(
                "response", messages, max_tokens=req.max_tokens or 100
            )
            content = response_result["choices"]["message"]["content"]
            content_validated, validation_meta = self._validate_output(content)

            # Chunking temporal
            chunks = [
                content_validated[i : i + 50]
                for i in range(0, len(content_validated), 50)
            ]
            ttft = time.time() - start_time

            for i, chunk in enumerate(chunks):
                if i == 0:
                    yield f"data: {json.dumps({'type': 'ttft', 'latency_ms': int(ttft * 1000)})}\n\n"
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                await asyncio.sleep(0.05)  # 50ms chunking

            total_time = time.time() - start_time
            yield f"data: {json.dumps({'type': 'final', 'model': 'smx_local_unified', 'latency_ms': int(total_time * 1000), 'ttft_ms': int(ttft * 1000), 'output_validation': validation_meta})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return router
