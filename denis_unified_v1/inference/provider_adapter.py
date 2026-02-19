"""Unified ProviderAdapter ABC + thin wrappers for existing clients.

Each adapter wraps an existing client (LlamaCppClient, GroqClient, etc.)
and normalizes request/response to ProviderCallResult.
The original clients are NOT modified — this is a wrapper layer.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .gateway_types import ProviderCallResult


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class ProviderAdapter(ABC):
    """Unified interface for all inference providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Canonical provider identifier (e.g. 'llamacpp', 'groq')."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float = 5.0,
        **params: Any,
    ) -> ProviderCallResult:
        """Send chat completion request, return normalized result."""
        ...

    async def stream(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float = 5.0,
        **params: Any,
    ) -> ProviderCallResult:
        """Streaming variant. Default: delegates to chat()."""
        return await self.chat(messages, timeout_sec, **params)

    @abstractmethod
    def is_available(self) -> bool:
        """Quick check: can this provider accept requests right now?"""
        ...

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate USD cost for given token counts. Override per provider."""
        return 0.0


# ---------------------------------------------------------------------------
# Helper: wrap a legacy generate() call into ProviderCallResult
# ---------------------------------------------------------------------------

def _wrap_generate(
    provider: str,
    model: str,
    cost_factor: float,
    result: Dict[str, Any],
    elapsed_ms: float,
) -> ProviderCallResult:
    """Convert the legacy {response, input_tokens, output_tokens, raw} dict."""
    inp = int(result.get("input_tokens") or 0)
    out = int(result.get("output_tokens") or 0)
    cost = cost_factor * (inp + out) / 1000.0
    return ProviderCallResult(
        provider=provider,
        model=model,
        response=str(result.get("response") or ""),
        input_tokens=inp,
        output_tokens=out,
        latency_ms=elapsed_ms,
        cost_usd_estimated=cost,
        raw=result.get("raw"),
        success=True,
    )


def _error_result(provider: str, model: str, error: str, elapsed_ms: float) -> ProviderCallResult:
    return ProviderCallResult(
        provider=provider,
        model=model,
        error=error,
        latency_ms=elapsed_ms,
        success=False,
    )


# ---------------------------------------------------------------------------
# LlamaCpp adapter
# ---------------------------------------------------------------------------

class LlamaCppAdapter(ProviderAdapter):
    """Wraps inference.llamacpp_client.LlamaCppClient."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def provider_name(self) -> str:
        return "llamacpp"

    def is_available(self) -> bool:
        return self._client.is_available()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self._client.cost_factor * (input_tokens + output_tokens) / 1000.0

    async def chat(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float = 5.0,
        **params: Any,
    ) -> ProviderCallResult:
        t0 = time.monotonic()
        try:
            result = await self._client.generate(messages, timeout_sec, **params)
            elapsed = (time.monotonic() - t0) * 1000
            return _wrap_generate("llamacpp", "local", self._client.cost_factor, result, elapsed)
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return _error_result("llamacpp", "local", str(exc), elapsed)


# ---------------------------------------------------------------------------
# Groq adapter
# ---------------------------------------------------------------------------

class GroqAdapter(ProviderAdapter):
    """Wraps inference.groq_client.GroqClient."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def provider_name(self) -> str:
        return "groq"

    def is_available(self) -> bool:
        return self._client.is_available()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self._client.cost_factor * (input_tokens + output_tokens) / 1000.0

    async def chat(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float = 5.0,
        **params: Any,
    ) -> ProviderCallResult:
        t0 = time.monotonic()
        try:
            result = await self._client.generate(messages, timeout_sec)
            elapsed = (time.monotonic() - t0) * 1000
            return _wrap_generate("groq", self._client.model, self._client.cost_factor, result, elapsed)
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return _error_result("groq", self._client.model, str(exc), elapsed)


# ---------------------------------------------------------------------------
# OpenRouter adapter
# ---------------------------------------------------------------------------

class OpenRouterAdapter(ProviderAdapter):
    """Wraps inference.openrouter_client.OpenRouterClient."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def is_available(self) -> bool:
        return self._client.is_available()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self._client.cost_factor * (input_tokens + output_tokens) / 1000.0

    async def chat(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float = 5.0,
        **params: Any,
    ) -> ProviderCallResult:
        t0 = time.monotonic()
        try:
            result = await self._client.generate(messages, timeout_sec)
            elapsed = (time.monotonic() - t0) * 1000
            return _wrap_generate(
                "openrouter", self._client.model, self._client.cost_factor, result, elapsed,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return _error_result("openrouter", self._client.model, str(exc), elapsed)


# ---------------------------------------------------------------------------
# Anthropic (Claude) adapter
# ---------------------------------------------------------------------------

class AnthropicAdapter(ProviderAdapter):
    """Wraps inference.claude_client.ClaudeClient."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        return self._client.is_available()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self._client.cost_factor * (input_tokens + output_tokens) / 1000.0

    async def chat(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float = 5.0,
        **params: Any,
    ) -> ProviderCallResult:
        t0 = time.monotonic()
        try:
            result = await self._client.generate(messages, timeout_sec)
            elapsed = (time.monotonic() - t0) * 1000
            return _wrap_generate(
                "anthropic", self._client.model, self._client.cost_factor, result, elapsed,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return _error_result("anthropic", self._client.model, str(exc), elapsed)


# ---------------------------------------------------------------------------
# vLLM adapter
# ---------------------------------------------------------------------------

class VLLMAdapter(ProviderAdapter):
    """Wraps inference.vllm_client.VLLMClient."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def provider_name(self) -> str:
        return "vllm"

    def is_available(self) -> bool:
        return self._client.is_available()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self._client.cost_factor * (input_tokens + output_tokens) / 1000.0

    async def chat(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float = 5.0,
        **params: Any,
    ) -> ProviderCallResult:
        t0 = time.monotonic()
        try:
            result = await self._client.generate(messages, timeout_sec)
            elapsed = (time.monotonic() - t0) * 1000
            return _wrap_generate("vllm", self._client.model, self._client.cost_factor, result, elapsed)
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return _error_result("vllm", self._client.model, str(exc), elapsed)
