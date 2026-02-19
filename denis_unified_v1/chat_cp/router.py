"""Chat control-plane router with fallback, retry, and circuit breaker."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from dataclasses import replace
import os
import time
from typing import Any
import uuid

from denis_unified_v1.chat_cp.contracts import ChatError, ChatRequest, ChatResponse
from denis_unified_v1.chat_cp.errors import ChatProviderError, hash_text
from denis_unified_v1.chat_cp.graph_trace import append_decision, init_run, set_outcome
from denis_unified_v1.chat_cp.providers.anthropic_chat import AnthropicChatProvider
from denis_unified_v1.chat_cp.providers.base import ChatProvider
from denis_unified_v1.chat_cp.providers.local_chat import LocalChatProvider
from denis_unified_v1.chat_cp.providers.openai_chat import OpenAIChatProvider
from denis_unified_v1.kernel.internet_health import get_internet_health


@dataclass(frozen=True)
class RoutingPolicy:
    policy_id: str = "control_plane_chat_default"
    default_chain: tuple[str, ...] = ("anthropic", "openai", "local")
    retries_max: int = 2
    backoff_ms: tuple[int, ...] = (250, 1000)
    circuit_fail_threshold: int = 5
    circuit_cooldown_seconds: int = 30


@dataclass
class CircuitState:
    failures: int = 0
    open_until_epoch: float = 0.0


class ChatRouter:
    def __init__(
        self,
        providers: dict[str, ChatProvider] | None = None,
        policy: RoutingPolicy | None = None,
    ) -> None:
        self.providers: dict[str, ChatProvider] = providers or {
            "anthropic": AnthropicChatProvider(),
            "openai": OpenAIChatProvider(),
            "local": LocalChatProvider(),
        }
        self.policy = policy or RoutingPolicy()
        self._circuit: dict[str, CircuitState] = {
            key: CircuitState() for key in self.providers.keys()
        }

    async def route(
        self,
        request: ChatRequest,
        *,
        fail_open: bool = True,
        shadow_mode: bool = False,
        policy_override: RoutingPolicy | None = None,
        strict_mode: bool | None = None,
    ) -> ChatResponse:
        policy = policy_override or self.policy
        strict = bool(strict_mode) if strict_mode is not None else (os.getenv("DENIS_CHAT_CP_STRICT", "0") == "1")
        run_id = request.trace_id or str(uuid.uuid4())
        request = replace(request, trace_id=run_id)

        chain = self._choose_chain(
            request,
            policy,
            apply_json_preference=policy_override is None,
        )
        if strict and chain:
            chain = [chain[0]]
        init_run(run_id=run_id, policy_id=policy.policy_id, chain=chain)
        last_error_code: str | None = None

        if shadow_mode and len(chain) > 1:
            append_decision(
                run_id,
                policy_id=policy.policy_id,
                provider=chain[1],
                status="shadow_candidate",
                latency_ms=0,
                error_code=None,
                message_hash=self._message_hash(request),
                shadow=True,
            )

        for provider_name in chain:
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            if provider_name != "local" and not provider.is_configured():
                append_decision(
                    run_id,
                    policy_id=policy.policy_id,
                    provider=provider_name,
                    status="not_configured",
                    latency_ms=0,
                    error_code="missing_secret",
                    message_hash=self._message_hash(request),
                )
                continue
            if self._is_circuit_open(provider_name):
                append_decision(
                    run_id,
                    policy_id=policy.policy_id,
                    provider=provider_name,
                    status="circuit_open",
                    latency_ms=0,
                    error_code="circuit_open",
                    message_hash=self._message_hash(request),
                )
                continue

            response, provider_error_code = await self._try_provider_with_retry(
                provider_name,
                provider,
                request,
                policy,
            )
            if response is not None:
                if response.trace_id is None:
                    response.trace_id = run_id
                append_decision(
                    run_id,
                    policy_id=policy.policy_id,
                    provider=provider_name,
                    status="ok",
                    latency_ms=response.latency_ms,
                    error_code=None,
                    message_hash=self._message_hash(request),
                )
                set_outcome(
                    run_id,
                    decision_id=None,
                    provider=provider_name,
                    success=True,
                    latency_ms=response.latency_ms,
                    error_code=None,
                )
                return response

            if provider_error_code is not None:
                last_error_code = str(provider_error_code)
            append_decision(
                run_id,
                policy_id=policy.policy_id,
                provider=provider_name,
                status="failed",
                latency_ms=0,
                error_code=provider_error_code,
                message_hash=self._message_hash(request),
            )

            if strict:
                break

        if fail_open and not strict:
            local = self.providers.get("local")
            if local is not None:
                try:
                    local_response = await local.chat(request)
                    if local_response.trace_id is None:
                        local_response.trace_id = run_id
                    append_decision(
                        run_id,
                        policy_id=policy.policy_id,
                        provider="local",
                        status="fail_open",
                        latency_ms=local_response.latency_ms,
                        error_code="fail_open",
                        message_hash=self._message_hash(request),
                    )
                    set_outcome(
                        run_id,
                        decision_id=None,
                        provider="local",
                        success=True,
                        latency_ms=local_response.latency_ms,
                        error_code="fail_open",
                    )
                    return local_response
                except ChatProviderError as exc:
                    last_error_code = exc.code
                    append_decision(
                        run_id,
                        policy_id=policy.policy_id,
                        provider="local",
                        status="failed",
                        latency_ms=0,
                        error_code=exc.code,
                        message_hash=self._message_hash(request),
                    )
                except Exception:
                    last_error_code = "server_error"
                    append_decision(
                        run_id,
                        policy_id=policy.policy_id,
                        provider="local",
                        status="failed",
                        latency_ms=0,
                        error_code="server_error",
                        message_hash=self._message_hash(request),
                    )

        final_code = last_error_code or "no_provider_available"
        fail_response = ChatResponse(
            text=None,
            json=None,
            provider="none",
            model=None,
            usage=None,
            latency_ms=0,
            success=False,
            error=ChatError(
                code=final_code,
                msg="all providers failed",
                retryable=False,
            ),
            trace_id=run_id,
        )
        set_outcome(
            run_id,
            decision_id=None,
            provider="none",
            success=False,
            latency_ms=0,
            error_code=final_code,
        )
        return fail_response

    async def _try_provider_with_retry(
        self,
        provider_name: str,
        provider: ChatProvider,
        request: ChatRequest,
        policy: RoutingPolicy,
    ) -> tuple[ChatResponse | None, str | None]:
        max_attempts = max(1, policy.retries_max + 1)
        last_error_code: str | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = await provider.chat(request)
                self._record_success(provider_name)
                return response, None
            except ChatProviderError as exc:
                last_error_code = exc.code
                self._record_failure(provider_name)
                if not exc.retryable or attempt >= max_attempts:
                    return None, last_error_code
                await asyncio.sleep(self._backoff_seconds(attempt, policy))
            except Exception:
                last_error_code = "server_error"
                self._record_failure(provider_name)
                if attempt >= max_attempts:
                    return None, last_error_code
                await asyncio.sleep(self._backoff_seconds(attempt, policy))

        return None, last_error_code

    def _choose_chain(
        self,
        request: ChatRequest,
        policy: RoutingPolicy,
        *,
        apply_json_preference: bool = True,
    ) -> list[str]:
        internet_ok = get_internet_health().is_internet_ok()
        preferred_provider = None
        if request.metadata:
            preferred_provider = request.metadata.get("preferred_provider")

        chain = list(policy.default_chain)
        if preferred_provider in chain:
            chain = [str(preferred_provider)] + [name for name in chain if name != preferred_provider]
        if apply_json_preference and request.response_format == "json" and "openai" in chain:
            chain = ["openai"] + [name for name in chain if name != "openai"]

        if not internet_ok:
            return ["local"]
        return chain

    def _is_circuit_open(self, provider_name: str) -> bool:
        state = self._circuit.setdefault(provider_name, CircuitState())
        return time.time() < state.open_until_epoch

    def _record_failure(self, provider_name: str) -> None:
        state = self._circuit.setdefault(provider_name, CircuitState())
        state.failures += 1
        if state.failures >= self.policy.circuit_fail_threshold:
            state.open_until_epoch = time.time() + float(self.policy.circuit_cooldown_seconds)

    def _record_success(self, provider_name: str) -> None:
        state = self._circuit.setdefault(provider_name, CircuitState())
        state.failures = 0
        state.open_until_epoch = 0.0

    @staticmethod
    def _message_hash(request: ChatRequest) -> str:
        body = "\n".join(msg.content for msg in request.messages)
        return hash_text(body)

    @staticmethod
    def _backoff_seconds(attempt: int, policy: RoutingPolicy) -> float:
        index = max(0, min(attempt - 1, len(policy.backoff_ms) - 1))
        return float(policy.backoff_ms[index]) / 1000.0
