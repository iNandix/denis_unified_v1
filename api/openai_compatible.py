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

from .sse_handler import stream_text_chunks


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
                                    for key in ("response", "answer", "text", "content"):
                                        val = data.get(key)
                                        if isinstance(val, str) and val.strip():
                                            return val.strip()
                    except Exception:
                        continue
        except Exception:
            pass

        return None

    async def generate(self, req: ChatCompletionRequest) -> dict[str, Any]:
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        user_text = self._extract_user_text(req.messages)
        prompt_tokens = max(1, len(user_text.split()))

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

        # Use cognitive router for routing decision if available
        routing_decision = None
        try:
            from denis_unified_v1.orchestration.cognitive_router import create_router as create_cognitive_router
            self.cognitive_router = create_cognitive_router()
            routing_decision = self.cognitive_router.route_decision(
                task=user_text,
                request_id=completion_id,
                context={"model_requested": req.model, "endpoint": "chat_completions"},
            )
        except Exception:
            self.cognitive_router = None
            routing_decision = None

        answer = ""
        path = "local_fallback"
        router_meta: dict[str, Any] = {}

        # Try inference router if available
        try:
            from denis_unified_v1.inference.router_v2 import create_inference_router
            self.inference_router = create_inference_router()
        except Exception:
            self.inference_router = None

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
                    }
                    if routing_decision:
                        router_meta["cognitive_routing"] = {
                            "tool_selected": routing_decision.tool_name,
                            "confidence": routing_decision.confidence,
                            "strategy": routing_decision.strategy.value,
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

        # Validación de salida
        validated_answer, validation_meta = self._validate_output(answer)
        completion_tokens = max(1, len(validated_answer.split()))

        # Record execution result in cognitive router if available
        if self.cognitive_router is not None and routing_decision is not None:
            try:
                self.cognitive_router.record_execution_result(
                    request_id=completion_id,
                    tool_name=routing_decision.tool_name,
                    success=bool(validated_answer),
                    error=None if validated_answer else "no_response",
                    execution_time_ms=0,
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
            self.flags = type("Flags", (), {
                "denis_use_voice_pipeline": False,
                "denis_use_memory_unified": False,
                "denis_use_atlas": False,
                "denis_use_inference_router": False,
                "phase10_enable_prompt_injection_guard": False,
                "phase10_max_output_tokens": 512,
            })()

        self.models = [{"id": "denis-cognitive", "object": "model"}]
        self.budget_manager = None

    async def generate(self, req: ChatCompletionRequest) -> dict[str, Any]:
        """Generate response using available backends."""
        # Check for deterministic test mode - ONLY in non-production environments
        env = os.getenv("ENV", "production")  # Default to production for safety
        
        is_contract_mode = (
            req.model == "denis-contract-test" and
            env != "production" and  # Never active in production
            os.getenv("DENIS_CONTRACT_TEST_MODE") == "1"
        )
        
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
            if hasattr(message, 'role') and hasattr(message, 'content'):
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
                "function": {
                    "name": "test_tool",
                    "arguments": '{"action": "test"}'
                }
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

    @router.get("/models")
    async def list_models() -> dict[str, Any]:
        try:
            return {"object": "list", "data": runtime.models}
        except Exception:
            # Fail-open degraded response
            return {"object": "list", "data": [{"id": "denis-cognitive", "object": "model"}]}

    @router.post("/chat/completions")
    async def chat_completions(req: ChatCompletionRequest, request: Request):
        ip = request.client.host if request.client else "unknown"
        user = ip

        try:
            result = await runtime.generate(req)
            return JSONResponse(status_code=200, content=result)
        except Exception as e:
            # Fail-open degraded response
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
                                "content": f"Degraded response: {str(e)}",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

    return router
