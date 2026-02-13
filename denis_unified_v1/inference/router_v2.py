"""Router v2 - Inference Router integration."""

from typing import Any, Dict, Optional
import asyncio
import time

from denis_unified_v1.feature_flags import load_feature_flags
from denis_unified_v1.observability.metrics import (
    inference_router_decisions,
    inference_router_latency,
    inference_engine_selection,
    gate_budget_exceeded,
    gate_rate_limited,
)
from denis_unified_v1.observability.tracing import get_tracer

from .engine_broker import EngineBroker, ExecutionResult
from .request_features import extract_request_features

tracer = get_tracer()


class InferenceRouterV2:
    def __init__(self):
        self.flags = load_feature_flags()
        self.broker = EngineBroker()

        # Fase 10: estado in-memory para rate limiting tipo token bucket.
        # Si se requiere Redis más adelante, se puede migrar sin cambiar la interfaz.
        self._rate_limit_state: Dict[str, Dict[str, float]] = {}

    def _rate_limit_key(self, request: Dict, class_key: str) -> str:
        """Construye la clave de rate limit (por user_id si existe, si no por class_key)."""
        user_id = str(request.get("user_id") or "").strip()
        if user_id:
            return f"user:{user_id}"
        return f"class:{class_key}"

    def _check_rate_limit(self, key: str) -> tuple[bool, int]:
        """Token bucket sencillo en memoria para Phase10.

        Devuelve (allowed, remaining_tokens_aprox).
        """
        # Si Fase 10 no está activa, nunca limita (por seguridad).
        if not getattr(self.flags, "denis_use_gate_hardening", False):
            return True, 0

        now = time.time()
        burst = float(getattr(self.flags, "phase10_rate_limit_burst", 16))
        rps = float(getattr(self.flags, "phase10_rate_limit_rps", 8))
        state = self._rate_limit_state.get(key)

        if state is None:
            tokens = burst
            last_ts = now
        else:
            tokens = float(state.get("tokens", burst))
            last_ts = float(state.get("last_ts", now))

        # Refill tokens según el tiempo transcurrido.
        elapsed = max(0.0, now - last_ts)
        tokens = min(burst, tokens + elapsed * rps)

        if tokens < 1.0:
            self._rate_limit_state[key] = {"tokens": tokens, "last_ts": now}
            return False, int(tokens)

        tokens -= 1.0
        self._rate_limit_state[key] = {"tokens": tokens, "last_ts": now}
        return True, int(tokens)

    async def route(self, request: Dict) -> Dict:
        start_time = time.perf_counter()

        with tracer.start_as_current_span("inference_router.route") as span:
            span.set_attribute("request.text", request.get("text", "")[:100])
            span.set_attribute("request.intent", request.get("intent", "chat"))

            features = extract_request_features(
                text=request.get("text", ""),
                intent=request.get("intent", "chat"),
                stream=request.get("stream", False),
                session_id=request.get("session_id"),
                user_id=request.get("user_id"),
            )

            span.set_attribute("features.class_key", features.class_key)
            span.set_attribute("features.len_chars", features.len_chars)

            shadow_mode = self.flags.phase7_router_shadow_mode
            decision = await self.broker.route(features, shadow_mode=shadow_mode)

            span.set_attribute("decision.engine_id", decision.engine_id)
            span.set_attribute("decision.reason", decision.reason)
            span.set_attribute("decision.shadow_mode", shadow_mode)

            latency = (time.perf_counter() - start_time) * 1000
            inference_router_decisions.labels(
                engine_id=decision.engine_id,
                reason=decision.reason,
                shadow_mode=str(shadow_mode),
            ).inc()
            inference_router_latency.observe(latency / 1000)
            inference_engine_selection.labels(
                engine_id=decision.engine_id, class_key=features.class_key
            ).inc()

            return {
                "engine_id": decision.engine_id,
                "class_key": features.class_key,
                "candidate_scores": decision.candidate_scores,
                "reason": decision.reason,
                "hedged_engine": decision.hedged_engine,
                "shadow_mode": shadow_mode,
                "enabled": self.flags.denis_use_inference_router,
                "latency_ms": latency,
            }

    async def execute(self, request: Dict) -> ExecutionResult:
        """Ejecuta una request de inferencia pasando por routing + gate básico (Phase10)."""
        route_result = await self.route(request)

        if route_result["shadow_mode"]:
            return ExecutionResult(
                result={"shadow_mode": True},
                engine_id=route_result["engine_id"],
                latency_ms=0,
                success=True,
            )

        # Fase 10: Gate Hardening (subset incremental: rate limiting + budget total).
        if getattr(self.flags, "denis_use_gate_hardening", False):
            # 1) Rate limiting (per user o por class_key).
            key = self._rate_limit_key(request, route_result["class_key"])
            allowed, remaining = self._check_rate_limit(key)
            if not allowed:
                scope = "user" if key.startswith("user:") else "class"
                gate_rate_limited.labels(scope=scope).inc()
                return ExecutionResult(
                    result={
                        "error": "rate_limited",
                        "detail": "Phase10 rate limit exceeded",
                        "key": key,
                        "retry_after_ms": 1000,
                        "remaining": remaining,
                    },
                    engine_id=route_result["engine_id"],
                    latency_ms=0,
                    success=False,
                )

            # 2) Budget total (timeout duro sobre la ejecución del engine).
            timeout_ms = int(getattr(self.flags, "phase10_budget_total_ms", 4500))
            timeout_sec = max(0.1, timeout_ms / 1000.0)

            try:
                result = await asyncio.wait_for(
                    self.broker.execute(
                        engine_id=route_result["engine_id"],
                        messages=request.get("messages", []),
                        stream=request.get("stream", False),
                        max_tokens=request.get("max_tokens"),
                    ),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                # Degradación controlada: no 500, sino contrato explícito de budget.
                gate_budget_exceeded.labels(budget="total").inc()
                return ExecutionResult(
                    result={
                        "error": "budget_exceeded",
                        "detail": "Phase10 total budget exceeded before completion",
                        "timeout_ms": timeout_ms,
                    },
                    engine_id=route_result["engine_id"],
                    latency_ms=timeout_ms,
                    success=False,
                )

            return result

        # Comportamiento previo (sin gate hardening).
        result = await self.broker.execute(
            engine_id=route_result["engine_id"],
            messages=request.get("messages", []),
            stream=request.get("stream", False),
            max_tokens=request.get("max_tokens"),
        )

        return result

    async def route_chat(self, messages: list, stream: bool = False) -> Dict:
        """Compatible interface for openai_compatible.py"""
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break

        request = {
            "text": user_text,
            "intent": "chat",
            "stream": stream,
            "messages": messages,
        }

        return await self.route(request)


def create_inference_router() -> InferenceRouterV2:
    return InferenceRouterV2()
