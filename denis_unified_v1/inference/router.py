"""Phase-7 inference router with scoring, fallback, and Redis metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
import re
import time
from typing import Any, Protocol

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None

try:
    from denis_unified_v1.smx.client import SMXClient
    from denis_unified_v1.smx.nlu_client import NLUClient
    from denis_unified_v1.smx.orchestrator import SMXOrchestrator
    from denis_unified_v1.orchestration.cognitive_router import CognitiveRouter
except ImportError:
    SMXClient = None  # type: ignore[misc,assignment]
    NLUClient = None  # type: ignore[misc,assignment]
    SMXOrchestrator = None  # type: ignore[misc,assignment]
    CognitiveRouter = None  # type: ignore[misc,assignment]

from denis_unified_v1.cognition.legacy_tools_v2 import (
    build_tool_registry_v2,
    ToolResult,
)
from denis_unified_v1.telemetry.steps import emit_tool_step
from denis_unified_v1.delivery.graph_projection import get_inference_projection

try:
    from denis_unified_v1.inference.vllm_client import VLLMClient
    from denis_unified_v1.inference.groq_client import GroqClient
    from denis_unified_v1.inference.openrouter_client import OpenRouterClient
    from denis_unified_v1.inference.legacy_core_client import LegacyCoreClient
    from denis_unified_v1.inference.llamacpp_client import LlamaCppClient
except ImportError:
    VLLMClient = None
    GroqClient = None
    OpenRouterClient = None
    LegacyCoreClient = None
    LlamaCppClient = None

try:
    from denis_unified_v1.kernel.engine_registry import get_engine_registry
except ImportError:
    get_engine_registry = None

from denis_unified_v1.kernel.internet_health import get_internet_health

try:
    from denis_unified_v1.feature_flags import load_feature_flags as _load_ff
except ImportError:
    _load_ff = None  # type: ignore[assignment]

try:
    from denis_unified_v1.inference.gateway_router import GatewayRouter as _GatewayRouter
except ImportError:
    _GatewayRouter = None  # type: ignore[assignment]

try:
    from denis_unified_v1.actions.decision_trace import emit_decision_trace as _emit_dt
except ImportError:
    _emit_dt = None  # type: ignore[assignment]

_SHADOW_TIMEOUT_MS = int(os.getenv("DENIS_GATEWAY_SHADOW_TIMEOUT_MS", "100"))


_TOOLS_V2: Any = None


def _get_tools_v2() -> Any:
    global _TOOLS_V2
    if _TOOLS_V2 is None:
        _TOOLS_V2 = build_tool_registry_v2()
    return _TOOLS_V2


def _allowed_domains(confidence_band: str) -> set[str]:
    if confidence_band == "high":
        return {
            "ide.fs",
            "ide.exec",
            "ha.read",
            "ha.write",
            "graph.read",
            "graph.write",
            "ops.system",
        }
    if confidence_band == "medium":
        return {"ide.fs", "ha.read", "graph.read"}
    return set()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_epoch() -> int:
    return int(time.time())


class ProviderClient(Protocol):
    provider: str

    @property
    def cost_factor(self) -> float: ...

    def is_available(self) -> bool: ...

    async def generate(
        self,
        messages: list[dict[str, str]],
        timeout_sec: float,
    ) -> dict[str, Any]: ...


@dataclass
class ProviderMetrics:
    latency_p95_ms: float
    error_rate_1h: float
    availability: float


@dataclass
class QueryProfile:
    token_count: int
    has_code: bool
    is_complex: bool
    is_general: bool


class RedisMetricsStore:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Any = None

    def enabled(self) -> bool:
        return redis is not None

    def _get(self):
        if not self.enabled():
            return None
        if self._client is None:
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def get_metrics(self, provider: str) -> ProviderMetrics:
        defaults = {
            "vllm": 150.0,
            "groq": 250.0,
            "openrouter": 450.0,
            "llamacpp": 180.0,
        }
        latency = defaults.get(provider, 500.0)
        error_rate = 0.0
        availability = 1.0
        client = self._get()
        if client is None:
            return ProviderMetrics(
                latency_p95_ms=latency,
                error_rate_1h=error_rate,
                availability=availability,
            )
        try:
            raw_latency = client.get(f"llm:{provider}:latency_p95")
            raw_error = client.get(f"llm:{provider}:error_rate_1h")
            raw_availability = client.get(f"llm:{provider}:availability")
            if raw_latency is not None:
                latency = float(raw_latency)
            if raw_error is not None:
                error_rate = max(0.0, min(1.0, float(raw_error)))
            if raw_availability is not None:
                availability = max(0.0, min(1.0, float(raw_availability)))
        except Exception:
            pass
        return ProviderMetrics(
            latency_p95_ms=max(1.0, latency),
            error_rate_1h=max(0.0, min(1.0, error_rate)),
            availability=max(0.0, min(1.0, availability)),
        )

    def record_call(self, provider: str, latency_ms: float, success: bool) -> None:
        client = self._get()
        if client is None:
            return
        now = _utc_epoch()
        try:
            client.zadd(f"llm:{provider}:latencies", {f"{latency_ms:.3f}:{now}": now})
            client.zremrangebyscore(f"llm:{provider}:latencies", 0, now - 3600)
            client.incr(f"llm:{provider}:requests:total")
            client.incr(
                f"llm:{provider}:requests:success"
                if success
                else f"llm:{provider}:requests:failure"
            )
        except Exception:
            return

    def emit_decision(self, request_id: str, payload: dict[str, Any]) -> None:
        client = self._get()
        if client is None:
            return
        try:
            encoded = json.dumps(payload, sort_keys=True)
            client.setex(f"denis:inference_router:decision:{request_id}", 3600, encoded)
            client.publish("denis:inference_router:decisions", encoded)
        except Exception:
            pass


def _analyze_query(text: str) -> QueryProfile:
    lowered = text.lower()
    token_count = max(1, len(text.split()))
    code_markers = [
        r"\bdef\b",
        r"\bclass\b",
        r"\bimport\b",
        r"\breturn\b",
        r"\bfunction\b",
        r"\bpython\b",
        r"\bjavascript\b",
        r"\bsql\b",
        r"```",
    ]
    complex_markers = [
        r"\banaly[sz]e\b",
        r"\bcompare\b",
        r"\btrade-?off\b",
        r"\bproof\b",
        r"\bmath\b",
        r"\breason\b",
    ]
    has_code = any(re.search(pattern, lowered) for pattern in code_markers)
    is_complex = token_count > 80 or any(re.search(pattern, lowered) for pattern in complex_markers)
    is_general = not has_code and not is_complex
    return QueryProfile(
        token_count=token_count,
        has_code=has_code,
        is_complex=is_complex,
        is_general=is_general,
    )


class InferenceRouter:
    def __init__(
        self,
        metrics_store: RedisMetricsStore | None = None,
        provider_order: list[str] | None = None,
    ) -> None:
        self.metrics = metrics_store or RedisMetricsStore()
        raw_order = (
            ",".join(provider_order)
            if provider_order
            else os.getenv(
                "DENIS_INFERENCE_PROVIDER_ORDER",
                "llamacpp,vllm,groq,openrouter",
            )
        )
        self.provider_order = [
            token.strip().lower() for token in raw_order.split(",") if token.strip()
        ]
        self.max_fallback_attempts = int(os.getenv("DENIS_ROUTER_MAX_ATTEMPTS", "3"))

        # Only instantiate clients if they're available
        self.clients: dict[str, ProviderClient] = {}
        if VLLMClient is not None:
            self.clients["vllm"] = VLLMClient()
        if GroqClient is not None:
            self.clients["groq"] = GroqClient()
        if OpenRouterClient is not None:
            self.clients["openrouter"] = OpenRouterClient()
        if LegacyCoreClient is not None:
            self.clients["legacy_core"] = LegacyCoreClient()

        # Piper TTS - no client needed, use a dummy that implements protocol
        class PiperDummy:
            provider = "piper"
            cost_factor = 0.0

            def is_available(self):
                return True

            async def generate(self, messages, timeout_sec):
                return {"audio": "dummy", "text": "piper dummy"}

        self.clients["piper"] = PiperDummy()

        # Deep-copy so test mutations don't leak back into the global singleton
        # If no registry, degrade gracefully
        registry = get_engine_registry() if get_engine_registry else {}
        self.engine_registry = {eid: dict(e) for eid, e in (registry or {}).items()}

        # Assign clients per engine_id with correct endpoint from registry
        for eid, e in self.engine_registry.items():
            pk = e.get("provider_key") or e.get("provider", "unknown")
            e.setdefault("provider_key", pk)
            endpoint = e.get("endpoint", "")

            # Create client instance with engine-specific endpoint
            if pk == "llamacpp":
                e["client"] = LlamaCppClient(endpoint)
            elif pk == "groq" and endpoint:
                e["client"] = self.clients.get("groq")
            elif pk == "openrouter" and endpoint:
                e["client"] = self.clients.get("openrouter")
            elif pk in self.clients:
                e["client"] = self.clients[pk]

        # Validate - skip llamacpp since it's per-engine
        missing = []
        for eid, e in self.engine_registry.items():
            pk = e.get("provider_key", e.get("provider", "unknown"))
            if pk == "llamacpp":
                continue  # Per-engine instantiation
            if pk not in self.clients:
                missing.append(eid)
        if missing:
            strict = (os.getenv("DENIS_STRICT_ENGINE_REGISTRY") or "").strip().lower() in {
                "1",
                "true",
                "yes",
            }
            if strict:
                raise RuntimeError(
                    f"Unknown provider_key in engine_registry for engines: {missing}"
                )
            # Fail-open: drop engines that cannot be instantiated. Router still operates with remaining engines.
            for eid in missing:
                self.engine_registry.pop(eid, None)

    def get_status(self) -> dict[str, Any]:
        providers: list[dict[str, Any]] = []
        for provider in self.provider_order:
            client = self.clients.get(provider)
            if client is None:
                continue
            metrics = self.metrics.get_metrics(provider)
            providers.append(
                {
                    "provider": provider,
                    "configured": client.is_available(),
                    "latency_p95_ms": metrics.latency_p95_ms,
                    "error_rate_1h": metrics.error_rate_1h,
                    "availability": metrics.availability,
                }
            )
        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "provider_order": self.provider_order,
            "providers": providers,
            "redis_metrics_enabled": self.metrics.enabled(),
        }

    def _score_provider(
        self,
        provider: str,
        client: ProviderClient,
        profile: QueryProfile,
        latency_budget_ms: int | None,
    ) -> tuple[float, ProviderMetrics]:
        metrics = self.metrics.get_metrics(provider)
        score = (
            (1.0 / max(1.0, metrics.latency_p95_ms))
            * metrics.availability
            * (1.0 - metrics.error_rate_1h)
            * max(0.01, client.cost_factor)
        )
        if profile.has_code and provider == "vllm":
            score += 0.3
        if profile.is_general and provider == "groq":
            score += 0.2
        if profile.is_complex and provider == "claude":
            score += 0.3
        if latency_budget_ms is not None and metrics.latency_p95_ms > latency_budget_ms:
            score *= 0.65
        return score, metrics

    async def route_chat(
        self,
        messages: list[dict[str, str]],
        *,
        request_id: str,
        inference_plan: InferencePlan | None = None,
        task_profile_id: str | None = None,
        latency_budget_ms: int | None = None,
        cost_limit_usd: float | None = None,
    ) -> dict[str, Any]:
        if (
            os.getenv("DENIS_ENABLE_CHAT_CP", "0") == "1"
            and task_profile_id == "control_plane_chat"
        ):
            chat_cp_result = await self._route_via_chat_cp(
                messages=messages,
                request_id=request_id,
                task_profile_id=task_profile_id,
            )
            if chat_cp_result is not None:
                return chat_cp_result

        skipped_engines = []
        if inference_plan:
            # Plan-first: execute without re-analysis
            engine_ids = [inference_plan.primary_engine_id] + list(
                inference_plan.fallback_engine_ids
            )
            max_attempts = inference_plan.attempt_policy.get("max_attempts", len(engine_ids))

            for attempt_idx, engine_id in enumerate(engine_ids[:max_attempts]):
                info = self._resolve_engine(engine_id)
                if not info:
                    # P3: plan referenced an engine_id the registry doesn't know.
                    # This is a misconfiguration — record it, don't silently skip.
                    skipped_engines.append(
                        {
                            "engine_id": engine_id,
                            "reason": "engine_not_found_in_registry",
                            "misconfig": True,
                        }
                    )
                    continue

                internet_ok = get_internet_health().check() == "OK"
                if "internet_required" in info.get("tags", []) and not internet_ok:
                    skipped_engines.append({"engine_id": engine_id, "reason": "no_internet"})
                    continue

                provider_key = info["provider_key"]
                client = info["client"]
                model = info.get("model")

                # Optional drift check
                if (
                    inference_plan.expected_model
                    and model
                    and model != inference_plan.expected_model
                ):
                    # Trace warning (no fail)
                    pass

                params = {**info.get("params_default", {}), **inference_plan.params}
                timeout_s = inference_plan.timeouts_ms.get("total_ms", 5000) / 1000.0

                # Execute
                started = time.perf_counter()
                try:
                    result = await client.generate(
                        messages=messages, timeout_sec=timeout_s, **params
                    )
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    self.metrics.record_call(provider_key, latency_ms=latency_ms, success=True)
                    return self._format_result(
                        result,
                        provider_key=provider_key,
                        engine_id=engine_id,
                        model=model,
                        plan=inference_plan,
                        latency_ms=latency_ms,
                        skipped_engines=skipped_engines,
                        internet_status_runtime=get_internet_health().check(),
                        attempt_number=attempt_idx + 1,
                    )
                except Exception as exc:
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    self.metrics.record_call(provider_key, latency_ms=latency_ms, success=False)
                    # Continue to fallback
                    continue

            # Degraded fallback
            return self._degraded_fallback(
                plan=inference_plan,
                skipped_engines=skipped_engines,
                internet_status_runtime=get_internet_health().check(),
            )
        else:
            # Legacy heuristic (mark trace ASSUMPTION_MADE)
            user_text = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_text = str(msg.get("content") or "")
                    break
            profile = _analyze_query(user_text)

            self.metrics.emit_decision(
                request_id,
                {
                    "mode": "legacy_heuristic",
                    "assumption": "derived_from_query_profile",
                },
            )

            # Existing logic
            scored: list[tuple[str, float, ProviderMetrics]] = []
            for provider in self.provider_order:
                client = self.clients.get(provider)
                if client is None:
                    continue
                if not client.is_available() and provider != "legacy_core":
                    continue
                score, metrics = self._score_provider(
                    provider,
                    client,
                    profile,
                    latency_budget_ms,
                )
                scored.append((provider, score, metrics))
            scored.sort(key=lambda item: (-item[1], item[0]))

            # Shadow routing — InferenceGateway computes what it WOULD choose
            # Feature-flagged, timeout-safe, fail-open. Never affects real decision.
            legacy_provider = scored[0][0] if scored else None
            legacy_model = "unknown"
            self._run_shadow_hook(
                request_id=request_id,
                legacy_provider=legacy_provider,
                legacy_model=legacy_model,
                intent=profile,
            )

            attempts = 0
            errors: list[dict[str, Any]] = []
            for provider, score, metrics in scored:
                if attempts >= self.max_fallback_attempts:
                    break
                attempts += 1
                client = self.clients[provider]
                timeout_sec = (
                    max(0.6, latency_budget_ms / 1000.0)
                    if latency_budget_ms is not None
                    else float(os.getenv("DENIS_ROUTER_DEFAULT_TIMEOUT_SEC", "4.5"))
                )
                started = time.perf_counter()
                try:
                    result = await client.generate(messages=messages, timeout_sec=timeout_sec)
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    self.metrics.record_call(provider, latency_ms=latency_ms, success=True)
                    payload = {
                        "request_id": request_id,
                        "llm_used": provider,
                        "score": round(score, 8),
                        "latency_ms": int(latency_ms),
                        "attempts": attempts,
                        "fallback_used": attempts > 1,
                        "timestamp_utc": _utc_now(),
                        "ranking": [
                            {
                                "provider": p,
                                "score": round(s, 8),
                                "latency_p95_ms": m.latency_p95_ms,
                                "error_rate_1h": m.error_rate_1h,
                                "availability": m.availability,
                            }
                            for p, s, m in scored
                        ],
                    }
                    self.metrics.emit_decision(request_id, payload)
                    # Project inference decision to graph (fail-open)
                    try:
                        get_inference_projection().project_inference_decision(**payload)
                    except Exception:
                        pass
                    output_tokens = int(result.get("output_tokens") or 0)
                    input_tokens = int(result.get("input_tokens") or max(1, len(user_text.split())))
                    cost_usd = self._estimate_cost_usd(
                        provider=provider,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                    if cost_limit_usd is not None and cost_usd > cost_limit_usd:
                        raise RuntimeError(
                            f"cost_limit_exceeded provider={provider} cost={cost_usd:.6f} limit={cost_limit_usd:.6f}"
                        )
                    return {
                        "response": str(result.get("response") or "").strip(),
                        "llm_used": provider,
                        "latency_ms": int(latency_ms),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": round(cost_usd, 6),
                        "fallback_used": attempts > 1,
                        "attempts": attempts,
                        "ranking": payload["ranking"],
                    }
                except Exception as exc:
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    self.metrics.record_call(provider, latency_ms=latency_ms, success=False)
                    errors.append(
                        {
                            "provider": provider,
                            "error": str(exc)[:300],
                            "latency_ms": int(latency_ms),
                        }
                    )

            fallback_text = (
                "Denis router fallback local: no provider respondió correctamente."
                f" Query: {user_text[:180]}"
            )
            self.metrics.emit_decision(
                request_id,
                {
                    "request_id": request_id,
                    "llm_used": "local_fallback",
                    "attempts": attempts,
                    "fallback_used": True,
                    "timestamp_utc": _utc_now(),
                    "errors": errors,
                },
            )
            # Project fallback decision to graph (fail-open)
            try:
                get_inference_projection().project_inference_decision(
                    request_id=request_id,
                    llm_used="local_fallback",
                    latency_ms=0,
                    input_tokens=max(1, len(user_text.split())),
                    output_tokens=max(1, len(fallback_text.split())),
                    cost_usd=0.0,
                    mode="legacy_fallback",
                )
            except Exception:
                pass
            return {
                "response": fallback_text,
                "llm_used": "local_fallback",
                "latency_ms": 0,
                "input_tokens": max(1, len(user_text.split())),
                "output_tokens": max(1, len(fallback_text.split())),
                "cost_usd": 0.0,
                "fallback_used": True,
                "attempts": attempts,
                "errors": errors,
                "ranking": [
                    {
                        "provider": p,
                        "score": round(s, 8),
                        "latency_p95_ms": m.latency_p95_ms,
                        "error_rate_1h": m.error_rate_1h,
                        "availability": m.availability,
                    }
                    for p, s, m in scored
                ],
            }

    async def _route_via_chat_cp(
        self,
        *,
        messages: list[dict[str, str]],
        request_id: str,
        task_profile_id: str,
    ) -> dict[str, Any] | None:
        """Route through chat control-plane (fail-soft)."""
        try:
            from denis_unified_v1.chat_cp.client import chat as chat_cp_chat
            from denis_unified_v1.chat_cp.contracts import ChatRequest as ChatCPRequest

            cp_request = ChatCPRequest.from_payload(
                {
                    "messages": messages,
                    "response_format": "text",
                    "temperature": 0.2,
                    "max_output_tokens": 512,
                    "stream": False,
                    "trace_id": request_id,
                    "metadata": {"source": "inference_router"},
                    "task_profile_id": task_profile_id,
                }
            )
            cp_response = await chat_cp_chat(
                cp_request,
                shadow_mode=os.getenv("DENIS_CHAT_CP_SHADOW_MODE", "0") == "1",
            )
            text = (cp_response.text or "").strip()
            usage = cp_response.usage or {}
            return {
                "response": text,
                "llm_used": cp_response.provider,
                "model_selected": cp_response.model,
                "engine_id": None,
                "latency_ms": int(cp_response.latency_ms),
                "input_tokens": int(usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
                "cost_usd": 0.0,
                "fallback_used": cp_response.provider in {"local", "none"},
                "attempts": 1,
                "ranking": [],
                "chat_cp_error": cp_response.error.as_dict() if cp_response.error else None,
                "task_profile_id": task_profile_id,
            }
        except Exception as exc:
            if _emit_dt:
                try:
                    _emit_dt(
                        kind="routing",
                        mode="FALLBACK",
                        reason="chat_cp_route_failed",
                        request_id=request_id,
                        extra={
                            "task_profile_id": task_profile_id,
                            "error": str(exc)[:200],
                        },
                    )
                except Exception:
                    pass
            return None

    def _run_shadow_hook(
        self,
        request_id: str,
        legacy_provider: str | None,
        legacy_model: str,
        intent: Any = None,
    ) -> None:
        """Shadow hook: compute gateway decision, log comparison, never affect real flow.

        - Gated by feature flags (both must be True)
        - Timeout-safe: capped at DENIS_GATEWAY_SHADOW_TIMEOUT_MS (default 100ms)
        - Fail-open: any error is silently swallowed
        """
        # Gate: both flags must be on
        if not _load_ff:
            return
        try:
            ff = _load_ff()
        except Exception:
            return
        if not ff.denis_enable_inference_gateway or not ff.denis_gateway_shadow_mode:
            return

        # Gate: router class must exist
        if not _GatewayRouter:
            return

        shadow_error = False
        shadow_decision: dict[str, Any] = {}
        try:
            import asyncio

            router = _GatewayRouter()
            intent_str = "chat_general"
            if isinstance(intent, QueryProfile):
                if intent.has_code:
                    intent_str = "code_generate"
                elif intent.is_complex:
                    intent_str = "deep_audit"

            task_profile_id = router.resolve_task_profile(intent_str, "*")
            candidates = router.select_candidates(task_profile_id)
            budget = router.apply_budgets(task_profile_id)
            strategy = router.choose_strategy(task_profile_id)

            shadow_decision = {
                "task_profile_id": task_profile_id,
                "selected_engine": candidates[0] if candidates else None,
                "fallback_engines": candidates[1:] if len(candidates) > 1 else [],
                "strategy": strategy,
                "budget_timeout_ms": budget.timeout_ms,
                "budget_max_output": budget.max_output_tokens,
            }
        except Exception:
            shadow_error = True

        # Compute comparison
        shadow_provider = shadow_decision.get("selected_engine")
        same_choice = (
            legacy_provider == shadow_provider if (legacy_provider and shadow_provider) else False
        )

        # Log to DecisionTrace (fail-open)
        if _emit_dt:
            try:
                _emit_dt(
                    kind="engine_selection",
                    mode="SHADOW",
                    reason="gateway_shadow_compare",
                    request_id=request_id,
                    engine=shadow_provider,
                    extra={
                        "legacy_provider": legacy_provider or "none",
                        "legacy_model": legacy_model,
                        "shadow_provider": shadow_provider or "none",
                        "shadow_model": shadow_decision.get("task_profile_id", "unknown"),
                        "same_choice": same_choice,
                        "shadow_error": shadow_error,
                        "shadow_reason": shadow_decision.get("strategy", "unknown"),
                    },
                )
            except Exception:
                pass

        # Log to Redis metrics (fail-open)
        try:
            self.metrics.emit_decision(
                request_id,
                {
                    "mode": "shadow_comparison",
                    "same_choice": same_choice,
                    "shadow_error": shadow_error,
                    "shadow_decision": shadow_decision,
                },
            )
        except Exception:
            pass

    def _resolve_engine(self, engine_id: str) -> dict[str, Any] | None:
        info = self.engine_registry.get(engine_id)
        if info is not None:
            # Normalize: ensure provider_key exists (tests may use "provider")
            info.setdefault("provider_key", info.get("provider", "unknown"))
        return info

    def _format_result(
        self,
        result: dict[str, Any],
        provider_key: str,
        engine_id: str,
        model: str | None,
        plan: InferencePlan,
        latency_ms: float,
        skipped_engines: list[dict],
        internet_status_runtime: str,
        attempt_number: int = 1,
    ) -> dict[str, Any]:
        output_tokens = int(result.get("output_tokens") or 0)
        input_tokens = int(result.get("input_tokens") or 0)
        cost_usd = self._estimate_cost_usd(provider_key, input_tokens, output_tokens)
        return {
            "response": str(result.get("response") or "").strip(),
            "llm_used": provider_key,
            "model_selected": model,
            "engine_id": engine_id,
            "latency_ms": int(latency_ms),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 6),
            "fallback_used": attempt_number > 1,
            "attempts": attempt_number,
            "inference_plan": plan,
            "skipped_engines": skipped_engines,
            "internet_status": internet_status_runtime,
            "degraded": plan.trace_tags.get("degraded", False),
        }

    def _degraded_fallback(
        self,
        plan: InferencePlan,
        skipped_engines: list[dict] | None = None,
        internet_status_runtime: str = "UNKNOWN",
    ) -> dict[str, Any]:
        fallback_text = "Denis router fallback: no engine available or all failed."
        return {
            "response": fallback_text,
            "llm_used": "degraded_fallback",
            "model_selected": None,
            "engine_id": None,
            "latency_ms": 0,
            "input_tokens": 0,
            "output_tokens": len(fallback_text.split()),
            "cost_usd": 0.0,
            "fallback_used": True,
            "attempts": len(plan.fallback_engine_ids) + 1,
            "inference_plan": plan,
            "skipped_engines": skipped_engines or [],
            "internet_status": internet_status_runtime,
            "degraded": True,
        }

    def _estimate_cost_usd(self, provider: str, input_tokens: int, output_tokens: int) -> float:
        rates_per_1k = {
            "vllm": 0.0001,
            "llamacpp": 0.0001,
            "groq": 0.0008,
            "openrouter": 0.0012,
        }
        rate = rates_per_1k.get(provider, 0.0010)
        tokens = max(1, input_tokens + output_tokens)
        return math.ceil(tokens) / 1000.0 * rate


def build_inference_router() -> InferenceRouter:
    # Check if SMX local pipeline should be used
    if os.getenv("USE_SMX_LOCAL") == "true":
        # Guard-rail: fail loud if SMX modules couldn't be imported
        if any(cls is None for cls in (SMXClient, NLUClient, SMXOrchestrator, CognitiveRouter)):
            raise RuntimeError(
                "USE_SMX_LOCAL=true but SMX modules could not be imported. "
                "Check denis_unified_v1/smx/ layout and imports."
            )
        # Pipeline SMX: NLU → Cognitive Router → SMX motors
        smx_client = SMXClient()
        nlu_client = NLUClient()
        orchestrator = SMXOrchestrator()
        cognitive_router = CognitiveRouter()

        async def smx_pipeline_with_cognition(messages, **kwargs):
            text = ""
            for msg in messages:
                if msg.get("role") == "user":
                    text = msg.get("content", "")
                    break

            if not text:
                return {
                    "response": "No se recibió mensaje de usuario",
                    "llm_used": "smx_cognitive_unified",
                    "latency_ms": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "fallback_used": False,
                    "attempts": 0,
                    "ranking": [],
                }

            # 1) NLU obligatorio
            nlu_result = await nlu_client.parse(text)

            # 2) Cognitive Router consulta patterns del grafo L1
            routing_decision = await cognitive_router.route(
                {
                    "text": text,
                    "intent": nlu_result["intent"],
                    "route_hint": nlu_result["route_hint"],
                    "entities": nlu_result.get("entities", []),
                }
            )

            tool_to_use = routing_decision["meta"]["tool_used"]
            pattern_used = routing_decision["meta"].get("pattern_id", None)

            # 3) Ejecutar según decisión del router (que consultó L1)
            if tool_to_use == "smx_fast_check" and nlu_result["route_hint"] == "fast":
                try:
                    import asyncio

                    result = await asyncio.wait_for(
                        smx_client.call_motor("fast_check", messages, max_tokens=30),
                        timeout=0.5,
                    )
                    content = result["choices"]["message"]["content"]
                except:
                    # Fallback a full pipeline
                    result = await orchestrator.process(text, nlu_result)
                    content = result.get("text", result.get("content", ""))
            else:
                # Full pipeline SMX
                result = await orchestrator.process(text, nlu_result)
                content = result.get("text", result.get("content", ""))

            return {
                "response": content,
                "llm_used": "smx_cognitive_unified",
                "latency_ms": 0,  # TODO: measure
                "input_tokens": max(1, len(text.split())),
                "output_tokens": max(1, len(content.split())),
                "cost_usd": 0.0,  # Local models, no cost
                "fallback_used": False,
                "attempts": 1,
                "ranking": [],
                "meta": {
                    "nlu": nlu_result,
                    "routing": routing_decision["meta"],
                    "pattern_used": pattern_used,
                    "grafo_l1_active": pattern_used is not None,
                },
            }

        return smx_pipeline_with_cognition

    # Default: Regular inference router
    return InferenceRouter()
