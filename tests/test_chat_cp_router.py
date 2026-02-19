from __future__ import annotations

import pytest

from denis_unified_v1.chat_cp.chat_router import ChatRouter, RoutingPolicy
from denis_unified_v1.chat_cp.contracts import ChatMessage, ChatRequest, ChatResponse
from denis_unified_v1.chat_cp.errors import ChatProviderError


class FakeProvider:
    def __init__(self, provider: str, outcomes):
        self.provider = provider
        self._outcomes = list(outcomes)
        self.calls = 0

    def is_configured(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        if self._outcomes:
            outcome = self._outcomes.pop(0)
        else:
            outcome = ChatResponse(
                text="ok",
                json=None,
                provider=self.provider,
                model=f"{self.provider}-model",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=10,
                trace_id=request.trace_id,
            )

        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class NotConfiguredProvider:
    def __init__(self, provider: str):
        self.provider = provider
        self.calls = 0

    def is_configured(self) -> bool:
        return False

    async def chat(self, request: ChatRequest) -> ChatResponse:
        _ = request
        self.calls += 1
        raise RuntimeError("should not be called")


def _request(response_format: str = "text") -> ChatRequest:
    return ChatRequest(
        messages=[ChatMessage(role="user", content="ping")],
        response_format=response_format,
        max_output_tokens=64,
        task_profile_id="control_plane_chat",
    )


@pytest.mark.asyncio
async def test_chat_router_primary_ok(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    anthropic = FakeProvider(
        "anthropic",
        [
            ChatResponse(
                text="primary ok",
                json=None,
                provider="anthropic",
                model="claude-test",
                usage={"input_tokens": 2, "output_tokens": 2},
                latency_ms=12,
            )
        ],
    )
    openai = FakeProvider("openai", [])
    local = FakeProvider("local", [])

    router = ChatRouter(
        providers={"anthropic": anthropic, "openai": openai, "local": local},
        policy=RoutingPolicy(default_chain=("anthropic", "openai", "local"), retries_max=0),
    )

    result = await router.route(_request())

    assert result.provider == "anthropic"
    assert result.text == "primary ok"
    assert anthropic.calls == 1
    assert openai.calls == 0


@pytest.mark.asyncio
async def test_chat_router_fallback_on_error(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    anthropic = FakeProvider(
        "anthropic",
        [ChatProviderError(code="anthropic_down", msg="boom", retryable=False)],
    )
    openai = FakeProvider(
        "openai",
        [
            ChatResponse(
                text="fallback ok",
                json=None,
                provider="openai",
                model="gpt-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=11,
            )
        ],
    )
    local = FakeProvider("local", [])

    router = ChatRouter(
        providers={"anthropic": anthropic, "openai": openai, "local": local},
        policy=RoutingPolicy(default_chain=("anthropic", "openai", "local"), retries_max=0),
    )

    result = await router.route(_request())

    assert result.provider == "openai"
    assert result.text == "fallback ok"
    assert anthropic.calls == 1
    assert openai.calls == 1


@pytest.mark.asyncio
async def test_chat_router_circuit_breaker(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    anthropic = FakeProvider(
        "anthropic",
        [
            ChatProviderError(code="down", msg="x", retryable=False),
            ChatProviderError(code="down", msg="y", retryable=False),
        ],
    )
    openai = FakeProvider(
        "openai",
        [
            ChatResponse(
                text="ok-1",
                json=None,
                provider="openai",
                model="gpt-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=10,
            ),
            ChatResponse(
                text="ok-2",
                json=None,
                provider="openai",
                model="gpt-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=10,
            ),
        ],
    )
    local = FakeProvider("local", [])

    router = ChatRouter(
        providers={"anthropic": anthropic, "openai": openai, "local": local},
        policy=RoutingPolicy(
            default_chain=("anthropic", "openai", "local"),
            retries_max=0,
            circuit_fail_threshold=1,
            circuit_cooldown_seconds=60,
        ),
    )

    first = await router.route(_request())
    second = await router.route(_request())

    assert first.provider == "openai"
    assert second.provider == "openai"
    assert anthropic.calls == 1
    assert openai.calls == 2


@pytest.mark.asyncio
async def test_chat_shadow_mode_no_effect(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    anthropic = FakeProvider(
        "anthropic",
        [
            ChatResponse(
                text="stable",
                json=None,
                provider="anthropic",
                model="claude-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=9,
            ),
            ChatResponse(
                text="stable",
                json=None,
                provider="anthropic",
                model="claude-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=9,
            ),
        ],
    )
    openai = FakeProvider("openai", [])
    local = FakeProvider("local", [])

    router = ChatRouter(
        providers={"anthropic": anthropic, "openai": openai, "local": local},
        policy=RoutingPolicy(default_chain=("anthropic", "openai", "local"), retries_max=0),
    )

    baseline = await router.route(_request(), shadow_mode=False)
    shadowed = await router.route(_request(), shadow_mode=True)

    assert baseline.provider == shadowed.provider == "anthropic"
    assert baseline.text == shadowed.text == "stable"
    assert anthropic.calls == 2


@pytest.mark.asyncio
async def test_contract_json_mode(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    anthropic = FakeProvider("anthropic", [])
    openai = FakeProvider(
        "openai",
        [
            ChatResponse(
                text=None,
                json={"ok": True, "source": "openai"},
                provider="openai",
                model="gpt-json",
                usage={"input_tokens": 3, "output_tokens": 4},
                latency_ms=13,
            )
        ],
    )
    local = FakeProvider("local", [])

    router = ChatRouter(
        providers={"anthropic": anthropic, "openai": openai, "local": local},
        policy=RoutingPolicy(default_chain=("anthropic", "openai", "local"), retries_max=0),
    )

    result = await router.route(_request(response_format="json"))

    assert result.provider == "openai"
    assert result.json == {"ok": True, "source": "openai"}
    assert result.error is None
    assert openai.calls == 1
    assert anthropic.calls == 0


@pytest.mark.asyncio
async def test_router_missing_secret_skips_provider_and_falls_back(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    anthropic = NotConfiguredProvider("anthropic")
    openai = FakeProvider(
        "openai",
        [
            ChatResponse(
                text="openai ok",
                json=None,
                provider="openai",
                model="gpt-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=8,
            )
        ],
    )
    local = FakeProvider("local", [])
    router = ChatRouter(
        providers={"anthropic": anthropic, "openai": openai, "local": local},
        policy=RoutingPolicy(default_chain=("anthropic", "openai", "local"), retries_max=0),
    )

    result = await router.route(_request())
    assert result.provider == "openai"
    assert anthropic.calls == 0
    assert openai.calls == 1


@pytest.mark.asyncio
async def test_router_network_error_retries_then_fallback(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    anthropic = FakeProvider(
        "anthropic",
        [
            ChatProviderError(code="network_error", msg="net-1", retryable=True),
            ChatProviderError(code="network_error", msg="net-2", retryable=True),
        ],
    )
    openai = FakeProvider(
        "openai",
        [
            ChatResponse(
                text="openai fallback",
                json=None,
                provider="openai",
                model="gpt-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=10,
            )
        ],
    )
    local = FakeProvider("local", [])

    router = ChatRouter(
        providers={"anthropic": anthropic, "openai": openai, "local": local},
        policy=RoutingPolicy(default_chain=("anthropic", "openai", "local"), retries_max=1),
    )

    result = await router.route(_request())
    assert result.provider == "openai"
    assert anthropic.calls == 2
    assert openai.calls == 1


@pytest.mark.asyncio
async def test_router_strict_mode_no_fallback(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    anthropic = FakeProvider(
        "anthropic",
        [ChatProviderError(code="missing_secret", msg="no key", retryable=False)],
    )
    openai = FakeProvider(
        "openai",
        [
            ChatResponse(
                text="openai ok",
                json=None,
                provider="openai",
                model="gpt-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=10,
            )
        ],
    )
    local = FakeProvider("local", [])

    router = ChatRouter(
        providers={"anthropic": anthropic, "openai": openai, "local": local},
        policy=RoutingPolicy(default_chain=("anthropic", "openai", "local"), retries_max=0),
    )

    result = await router.route(_request(), strict_mode=True, fail_open=True)
    assert result.provider == "none"
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "missing_secret"
    assert anthropic.calls == 1
    assert openai.calls == 0
