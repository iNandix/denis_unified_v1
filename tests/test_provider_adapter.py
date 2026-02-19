"""Tests for inference/provider_adapter.py — PR1 adapter wrappers."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from denis_unified_v1.inference.provider_adapter import (
    LlamaCppAdapter,
    GroqAdapter,
    OpenRouterAdapter,
    AnthropicAdapter,
    VLLMAdapter,
    ProviderAdapter,
)
from denis_unified_v1.inference.gateway_types import ProviderCallResult


def run(coro):
    """Sync helper for async tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_mock_client(
    provider: str = "test",
    model: str = "test-model",
    cost_factor: float = 0.01,
    available: bool = True,
    response: str = "Hello",
    input_tokens: int = 10,
    output_tokens: int = 5,
    fail: bool = False,
):
    """Create a mock client that mimics the legacy client interface."""
    client = MagicMock()
    client.provider = provider
    client.model = model
    client.cost_factor = cost_factor
    client.is_available.return_value = available
    client.endpoint = "http://localhost:9997"

    if fail:
        client.generate = AsyncMock(side_effect=RuntimeError("test_error_500"))
    else:
        client.generate = AsyncMock(return_value={
            "response": response,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "raw": {"test": True},
        })
    return client


# ---------------------------------------------------------------------------
# ABC contract
# ---------------------------------------------------------------------------

class TestProviderAdapterABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ProviderAdapter()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# LlamaCppAdapter
# ---------------------------------------------------------------------------

class TestLlamaCppAdapter:
    def test_provider_name(self):
        client = _make_mock_client()
        adapter = LlamaCppAdapter(client)
        assert adapter.provider_name == "llamacpp"

    def test_is_available(self):
        client = _make_mock_client(available=True)
        assert LlamaCppAdapter(client).is_available() is True
        client2 = _make_mock_client(available=False)
        assert LlamaCppAdapter(client2).is_available() is False

    def test_chat_success(self):
        client = _make_mock_client(response="World", input_tokens=20, output_tokens=10)
        adapter = LlamaCppAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "Hi"}], timeout_sec=5.0))
        assert isinstance(result, ProviderCallResult)
        assert result.success is True
        assert result.response == "World"
        assert result.input_tokens == 20
        assert result.output_tokens == 10
        assert result.provider == "llamacpp"
        assert result.latency_ms > 0

    def test_chat_error(self):
        client = _make_mock_client(fail=True)
        adapter = LlamaCppAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "Hi"}]))
        assert result.success is False
        assert "test_error_500" in result.error
        assert result.provider == "llamacpp"

    def test_estimate_cost(self):
        client = _make_mock_client(cost_factor=0.0001)
        adapter = LlamaCppAdapter(client)
        cost = adapter.estimate_cost(1000, 500)
        assert cost == pytest.approx(0.0001 * 1500 / 1000)

    def test_stream_delegates_to_chat(self):
        client = _make_mock_client(response="streamed")
        adapter = LlamaCppAdapter(client)
        result = run(adapter.stream([{"role": "user", "content": "Hi"}]))
        assert result.response == "streamed"


# ---------------------------------------------------------------------------
# GroqAdapter
# ---------------------------------------------------------------------------

class TestGroqAdapter:
    def test_provider_name(self):
        assert GroqAdapter(_make_mock_client()).provider_name == "groq"

    def test_chat_success(self):
        client = _make_mock_client(model="llama-3.1-70b", cost_factor=0.70)
        adapter = GroqAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "test"}]))
        assert result.success is True
        assert result.provider == "groq"
        assert result.model == "llama-3.1-70b"

    def test_chat_error_returns_result_not_exception(self):
        client = _make_mock_client(fail=True)
        adapter = GroqAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "test"}]))
        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# OpenRouterAdapter
# ---------------------------------------------------------------------------

class TestOpenRouterAdapter:
    def test_provider_name(self):
        assert OpenRouterAdapter(_make_mock_client()).provider_name == "openrouter"

    def test_chat_success(self):
        client = _make_mock_client(model="openai/gpt-4o-mini")
        adapter = OpenRouterAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "test"}]))
        assert result.success is True
        assert result.model == "openai/gpt-4o-mini"


# ---------------------------------------------------------------------------
# AnthropicAdapter
# ---------------------------------------------------------------------------

class TestAnthropicAdapter:
    def test_provider_name(self):
        assert AnthropicAdapter(_make_mock_client()).provider_name == "anthropic"

    def test_chat_success(self):
        client = _make_mock_client(model="claude-3-5-sonnet-20241022")
        adapter = AnthropicAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "test"}]))
        assert result.success is True
        assert result.provider == "anthropic"


# ---------------------------------------------------------------------------
# VLLMAdapter
# ---------------------------------------------------------------------------

class TestVLLMAdapter:
    def test_provider_name(self):
        assert VLLMAdapter(_make_mock_client()).provider_name == "vllm"

    def test_chat_success(self):
        client = _make_mock_client(model="deepseek-coder")
        adapter = VLLMAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "test"}]))
        assert result.success is True
        assert result.model == "deepseek-coder"

    def test_chat_error(self):
        client = _make_mock_client(fail=True, model="deepseek-coder")
        adapter = VLLMAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "test"}]))
        assert result.success is False


# ---------------------------------------------------------------------------
# Cross-adapter: all share the same contract
# ---------------------------------------------------------------------------

class TestAllAdaptersContract:
    """Verify all adapters return ProviderCallResult with the same fields."""

    @pytest.mark.parametrize("AdapterClass,provider_expected", [
        (LlamaCppAdapter, "llamacpp"),
        (GroqAdapter, "groq"),
        (OpenRouterAdapter, "openrouter"),
        (AnthropicAdapter, "anthropic"),
        (VLLMAdapter, "vllm"),
    ])
    def test_success_contract(self, AdapterClass, provider_expected):
        client = _make_mock_client()
        adapter = AdapterClass(client)
        result = run(adapter.chat([{"role": "user", "content": "hi"}]))
        assert isinstance(result, ProviderCallResult)
        assert result.provider == provider_expected
        assert result.success is True
        assert isinstance(result.response, str)
        assert isinstance(result.input_tokens, int)
        assert isinstance(result.output_tokens, int)
        assert isinstance(result.latency_ms, float)
        assert result.latency_ms >= 0

    @pytest.mark.parametrize("AdapterClass", [
        LlamaCppAdapter, GroqAdapter, OpenRouterAdapter, AnthropicAdapter, VLLMAdapter,
    ])
    def test_error_contract(self, AdapterClass):
        client = _make_mock_client(fail=True)
        adapter = AdapterClass(client)
        result = run(adapter.chat([{"role": "user", "content": "hi"}]))
        assert isinstance(result, ProviderCallResult)
        assert result.success is False
        assert result.error is not None
        assert isinstance(result.latency_ms, float)
