from __future__ import annotations

import pytest

from denis_unified_v1.chat_cp.chat_router import ChatRouter, RoutingPolicy
from denis_unified_v1.chat_cp.contracts import ChatMessage, ChatRequest, ChatResponse
from denis_unified_v1.chat_cp.errors import ChatProviderError


class AlwaysFailProvider:
    def __init__(self, provider: str):
        self.provider = provider

    def is_configured(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise ChatProviderError(code="provider_down", msg="down", retryable=False)


class LocalProvider:
    provider = "local"

    def is_configured(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            text="local fallback",
            json=None,
            provider="local",
            model="local",
            usage={"input_tokens": 0, "output_tokens": 0},
            latency_ms=1,
            success=False,
            trace_id=request.trace_id,
        )


@pytest.mark.asyncio
async def test_fail_open_fallback(monkeypatch):
    monkeypatch.setenv("DENIS_INTERNET_STATUS", "OK")

    router = ChatRouter(
        providers={
            "anthropic": AlwaysFailProvider("anthropic"),
            "openai": AlwaysFailProvider("openai"),
            "local": LocalProvider(),
        },
        policy=RoutingPolicy(default_chain=("anthropic", "openai", "local"), retries_max=0),
    )

    request = ChatRequest(
        messages=[ChatMessage(role="user", content="ping")],
        task_profile_id="control_plane_chat",
    )

    result = await router.route(request)

    assert result.provider == "local"
    assert result.text == "local fallback"
