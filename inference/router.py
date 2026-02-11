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

from denis_unified_v1.inference.claude_client import ClaudeClient
from denis_unified_v1.inference.groq_client import GroqClient
from denis_unified_v1.inference.legacy_core_client import LegacyCoreClient
from denis_unified_v1.inference.openrouter_client import OpenRouterClient
from denis_unified_v1.inference.vllm_client import VLLMClient


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
            "claude": 700.0,
            "legacy_core": 180.0,
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
            client.incr(f"llm:{provider}:requests:success" if success else f"llm:{provider}:requests:failure")
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
    is_complex = token_count > 80 or any(
        re.search(pattern, lowered) for pattern in complex_markers
    )
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
                "legacy_core,vllm,groq,openrouter,claude",
            )
        )
        self.provider_order = [
            token.strip().lower() for token in raw_order.split(",") if token.strip()
        ]
        self.max_fallback_attempts = int(os.getenv("DENIS_ROUTER_MAX_ATTEMPTS", "3"))
        self.clients: dict[str, ProviderClient] = {
            "legacy_core": LegacyCoreClient(),
            "vllm": VLLMClient(),
            "groq": GroqClient(),
            "openrouter": OpenRouterClient(),
            "claude": ClaudeClient(),
        }

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
        latency_budget_ms: int | None = None,
        cost_limit_usd: float | None = None,
    ) -> dict[str, Any]:
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = str(msg.get("content") or "")
                break
        profile = _analyze_query(user_text)

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

    def _estimate_cost_usd(self, provider: str, input_tokens: int, output_tokens: int) -> float:
        rates_per_1k = {
            "vllm": 0.0001,
            "legacy_core": 0.0001,
            "groq": 0.0008,
            "openrouter": 0.0012,
            "claude": 0.0030,
        }
        rate = rates_per_1k.get(provider, 0.0010)
        tokens = max(1, input_tokens + output_tokens)
        return math.ceil(tokens) / 1000.0 * rate


def build_inference_router() -> InferenceRouter:
    return InferenceRouter()
