"""Tests for ChatProviders layer."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestChatProviderBase:
    """Test base ChatProvider interface."""

    def test_chat_request_defaults(self):
        """Test ChatRequest has correct defaults."""
        from denis_unified_v1.inference.chat_providers import (
            ChatRequest,
            ResponseFormat,
        )

        req = ChatRequest(messages=[{"role": "user", "content": "Hello"}])

        assert req.max_tokens == 1024
        assert req.temperature == 0.7
        assert req.response_format == ResponseFormat.TEXT
        assert req.stream is False

    def test_chat_response_defaults(self):
        """Test ChatResponse has correct defaults."""
        from denis_unified_v1.inference.chat_providers import ChatResponse

        resp = ChatResponse()

        assert resp.text == ""
        assert resp.json is None
        assert resp.provider == ""
        assert resp.model == ""
        assert resp.success is True
        assert resp.error is None


class TestOpenAIAdapter:
    """Test OpenAI adapter."""

    def test_adapter_init(self):
        """Test adapter initialization."""
        from denis_unified_v1.inference.chat_providers import OpenAIChatAdapter

        adapter = OpenAIChatAdapter(api_key="test-key", model="gpt-4o-mini")

        assert adapter.info.provider == "openai"
        assert adapter.info.model == "gpt-4o-mini"
        assert adapter.is_available() is True

    def test_adapter_not_available_without_key(self):
        """Test adapter not available without API key."""
        import os
        from denis_unified_v1.inference.chat_providers import OpenAIChatAdapter

        with patch.dict(os.environ, {}, clear=True):
            adapter = OpenAIChatAdapter(api_key="")
            assert adapter.is_available() is False


class TestAnthropicAdapter:
    """Test Anthropic adapter."""

    def test_adapter_init(self):
        """Test adapter initialization."""
        from denis_unified_v1.inference.chat_providers import AnthropicChatAdapter

        adapter = AnthropicChatAdapter(
            api_key="test-key", model="claude-3-5-sonnet-20241022"
        )

        assert adapter.info.provider == "anthropic"
        assert adapter.info.model == "claude-3-5-sonnet-20241022"
        assert adapter.is_available() is True


class TestLocalAdapter:
    """Test Local adapter."""

    def test_adapter_init(self):
        """Test adapter initialization."""
        from denis_unified_v1.inference.chat_providers import LocalChatAdapter

        adapter = LocalChatAdapter(endpoint="http://localhost:8080/v1/chat/completions")

        assert adapter.info.provider == "local"
        assert adapter.info.cost_factor == 0.0
        assert adapter.is_available() is True


class TestRouter:
    """Test ChatProviderRouter."""

    def test_router_init(self):
        """Test router initialization."""
        from denis_unified_v1.inference.chat_providers import ChatProviderRouter

        router = ChatProviderRouter()

        assert router.config.primary == "openai"
        assert router.config.secondary == "anthropic"
        assert router.config.fallback == "local"

    def test_provider_chain(self):
        """Test provider chain selection."""
        from denis_unified_v1.inference.chat_providers import (
            ChatProviderRouter,
            TaskType,
        )

        router = ChatProviderRouter()

        # Test default chain
        chain = router._get_provider_chain(TaskType.CHAT)
        assert chain[0] == "openai"

        # Test JSON chain
        json_chain = router._get_provider_chain(TaskType.JSON_CHAT)
        assert json_chain[0] == "anthropic"

    def test_circuit_breaker(self):
        """Test circuit breaker logic."""
        from denis_unified_v1.inference.chat_providers.router import CircuitBreaker

        cb = CircuitBreaker(threshold=3, cooldown_ms=1000)

        # Record failures
        cb.record_failure("test_provider")
        cb.record_failure("test_provider")

        assert cb.is_open("test_provider") is False
        assert cb._failures["test_provider"] == 2

        # Reach threshold
        cb.record_failure("test_provider")

        assert cb.is_open("test_provider") is True
        assert cb._failures["test_provider"] >= 3

    def test_list_providers(self):
        """Test listing providers."""
        from denis_unified_v1.inference.chat_providers import ChatProviderRouter

        router = ChatProviderRouter()

        # All should be available (or some may not be configured)
        providers = router.list_providers()
        assert isinstance(providers, list)


class TestTaskType:
    """Test TaskType enum."""

    def test_task_types(self):
        """Test TaskType values."""
        from denis_unified_v1.inference.chat_providers import TaskType

        assert TaskType.CHAT.value == "chat"
        assert TaskType.FAST_CHAT.value == "fast_chat"
        assert TaskType.COMPLEX_CHAT.value == "complex_chat"
        assert TaskType.JSON_CHAT.value == "json_chat"


class TestChatCPProviders:
    """Tests for chat_cp provider secret behavior."""

    @pytest.mark.asyncio
    async def test_openai_chat_cp_missing_secret(self, monkeypatch):
        from denis_unified_v1.chat_cp.contracts import ChatMessage, ChatRequest
        from denis_unified_v1.chat_cp.errors import ChatProviderError
        import denis_unified_v1.chat_cp.providers.openai_chat as openai_mod

        def fail_secret(name: str):
            _ = name
            raise openai_mod.SecretError("backend down")

        monkeypatch.setattr(openai_mod, "ensure_secret", fail_secret)
        provider = openai_mod.OpenAIChatProvider()
        request = ChatRequest(
            messages=[ChatMessage(role="user", content="ping")],
            task_profile_id="control_plane_chat",
        )

        with pytest.raises(ChatProviderError) as exc:
            await provider.chat(request)

        assert exc.value.code == "missing_secret"

    def test_openai_http_auth_error_classification(self):
        import denis_unified_v1.chat_cp.providers.openai_chat as openai_mod

        err = openai_mod._map_openai_http_error(401, '{"error":{"message":"invalid api key"}}')
        assert err.code == "auth_error"
        assert err.retryable is False

    def test_anthropic_http_auth_error_classification(self):
        import denis_unified_v1.chat_cp.providers.anthropic_chat as anthropic_mod

        err = anthropic_mod._map_anthropic_http_error(
            401,
            '{"error":{"type":"authentication_error","message":"invalid key"}}',
        )
        assert err.code == "auth_error"
        assert err.retryable is False

    def test_openai_quota_is_quota_error(self):
        import denis_unified_v1.chat_cp.providers.openai_chat as openai_mod

        err = openai_mod._map_openai_http_error(
            429,
            '{"error":{"code":"insufficient_quota","message":"quota"}}',
        )
        assert err.code == "quota_error"

    @pytest.mark.asyncio
    async def test_anthropic_chat_cp_missing_secret(self, monkeypatch):
        from denis_unified_v1.chat_cp.contracts import ChatMessage, ChatRequest
        from denis_unified_v1.chat_cp.errors import ChatProviderError
        import denis_unified_v1.chat_cp.providers.anthropic_chat as anthropic_mod

        def fail_secret(name: str):
            _ = name
            raise anthropic_mod.SecretError("backend down")

        monkeypatch.setattr(anthropic_mod, "ensure_secret", fail_secret)
        provider = anthropic_mod.AnthropicChatProvider()
        request = ChatRequest(
            messages=[ChatMessage(role="user", content="ping")],
            task_profile_id="control_plane_chat",
        )

        with pytest.raises(ChatProviderError) as exc:
            await provider.chat(request)

        assert exc.value.code == "missing_secret"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
