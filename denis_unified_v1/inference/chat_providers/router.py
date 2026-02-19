#!/usr/bin/env python3
"""
ChatProvider Router - Fallback chain with circuit breaker.

Features:
- Provider selection by task_type
- Fallback chain: primary -> secondary -> local
- Circuit breaker basic
- Retry with backoff
- Shadow mode for A/B testing
"""

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .base import (
    ChatProvider,
    ChatProviderInfo,
    ChatRequest,
    ChatResponse,
    ResponseFormat,
)
from .openai_adapter import OpenAIChatAdapter
from .anthropic_adapter import AnthropicChatAdapter
from .local_adapter import LocalChatAdapter

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    CHAT = "chat"
    FAST_CHAT = "fast_chat"
    COMPLEX_CHAT = "complex_chat"
    JSON_CHAT = "json_chat"


@dataclass
class RouterConfig:
    """Router configuration."""

    primary: str = "openai"  # openai, anthropic
    secondary: str = "anthropic"
    fallback: str = "local"
    max_retries: int = 2
    retry_delays_ms: List[int] = field(default_factory=lambda: [250, 1000])
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown_ms: int = 60000
    shadow_mode: bool = os.getenv("DENIS_CHAT_SHADOW", "0") == "1"


class CircuitBreaker:
    """Basic circuit breaker for providers."""

    def __init__(self, threshold: int = 5, cooldown_ms: int = 60000):
        self.threshold = threshold
        self.cooldown_ms = cooldown_ms
        self._failures: Dict[str, int] = {}
        self._open_until: Dict[str, float] = {}

    def record_failure(self, provider: str):
        """Record a failure for provider."""
        self._failures[provider] = self._failures.get(provider, 0) + 1

        if self._failures[provider] >= self.threshold:
            self._open_until[provider] = time.time() * 1000 + self.cooldown_ms
            logger.warning(f"Circuit breaker OPEN for {provider}")

    def record_success(self, provider: str):
        """Record success, reset failures."""
        self._failures[provider] = 0
        self._open_until.pop(provider, None)

    def is_open(self, provider: str) -> bool:
        """Check if circuit is open for provider."""
        if provider not in self._open_until:
            return False

        if time.time() * 1000 > self._open_until[provider]:
            self._open_until.pop(provider, None)
            self._failures[provider] = 0
            return False

        return True


@dataclass
class ChatTelemetry:
    """Telemetry for chat requests."""

    provider: str
    model: str
    latency_ms: int
    success: bool
    error: Optional[str] = None
    fallback_used: bool = False
    shadow_provider: Optional[str] = None
    shadow_latency_ms: Optional[int] = None


class ChatProviderRouter:
    """Router for chat providers with fallback chain."""

    def __init__(self, config: Optional[RouterConfig] = None):
        self.config = config or RouterConfig()
        self.circuit_breaker = CircuitBreaker(
            threshold=self.config.circuit_breaker_threshold,
            cooldown_ms=self.config.circuit_breaker_cooldown_ms,
        )

        # Initialize providers
        self._providers: Dict[str, ChatProvider] = {}
        self._init_providers()

    def _init_providers(self):
        """Initialize all providers."""
        self._providers["openai"] = OpenAIChatAdapter()
        self._providers["anthropic"] = AnthropicChatAdapter()
        self._providers["local"] = LocalChatAdapter()

    def _get_provider_chain(self, task_type: TaskType) -> List[str]:
        """Get provider fallback chain for task type."""
        if task_type == TaskType.JSON_CHAT:
            return ["anthropic", "openai", "local"]
        elif task_type == TaskType.COMPLEX_CHAT:
            return ["anthropic", "openai", "local"]
        elif task_type == TaskType.FAST_CHAT:
            return ["openai", "local"]
        else:
            return [self.config.primary, self.config.secondary, self.config.fallback]

    def _select_provider(self, task_type: TaskType) -> Optional[ChatProvider]:
        """Select primary provider based on task type."""
        chain = self._get_provider_chain(task_type)

        for provider_name in chain:
            provider = self._providers.get(provider_name)
            if (
                provider
                and provider.is_available()
                and not self.circuit_breaker.is_open(provider_name)
            ):
                return provider

        return None

    async def chat(
        self,
        request: ChatRequest,
        task_type: TaskType = TaskType.CHAT,
    ) -> ChatResponse:
        """Execute chat with fallback chain."""

        # Determine task type from request if not specified
        if request.response_format == ResponseFormat.JSON:
            task_type = TaskType.JSON_CHAT

        chain = self._get_provider_chain(task_type)
        last_error = None

        for provider_name in chain:
            provider = self._providers.get(provider_name)

            if not provider:
                continue

            if not provider.is_available():
                logger.info(f"Provider {provider_name} not available, trying next")
                continue

            if self.circuit_breaker.is_open(provider_name):
                logger.info(f"Provider {provider_name} circuit open, trying next")
                continue

            # Try with retries
            for attempt in range(self.config.max_retries + 1):
                try:
                    response = await provider.chat(request)

                    if response.success:
                        self.circuit_breaker.record_success(provider_name)
                        logger.info(
                            f"Chat succeeded with {provider_name} in {response.latency_ms}ms"
                        )
                        return response

                    # Failure
                    last_error = response.error
                    self.circuit_breaker.record_failure(provider_name)
                    logger.warning(
                        f"Chat failed with {provider_name}: {response.error}"
                    )

                    # Retry with backoff
                    if attempt < self.config.max_retries:
                        delay = self.config.retry_delays_ms[attempt] / 1000.0
                        time.sleep(delay)

                except Exception as e:
                    last_error = str(e)
                    self.circuit_breaker.record_failure(provider_name)
                    logger.warning(f"Chat exception with {provider_name}: {e}")
                    break

        # All providers failed
        return ChatResponse(
            error=f"all_providers_failed: {last_error}",
            success=False,
        )

    async def chat_with_shadow(
        self,
        request: ChatRequest,
        task_type: TaskType = TaskType.CHAT,
    ) -> tuple[ChatResponse, Optional[ChatResponse]]:
        """
        Execute chat with shadow mode.

        Returns:
            (primary_response, shadow_response)
        """
        # Primary path
        primary = await self.chat(request, task_type)

        # Shadow path
        shadow_response = None
        if self.config.shadow_mode:
            # Use different provider for shadow
            chain = self._get_provider_chain(task_type)
            shadow_provider_name = chain[1] if len(chain) > 1 else chain[0]

            shadow_provider = self._providers.get(shadow_provider_name)
            if shadow_provider and shadow_provider.is_available():
                try:
                    shadow_response = await shadow_provider.chat(request)
                    logger.info(
                        f"[SHADOW] {shadow_provider_name}: {shadow_response.latency_ms}ms, "
                        f"success={shadow_response.success}"
                    )
                except Exception as e:
                    logger.warning(f"[SHADOW] {shadow_provider_name} failed: {e}")

        return primary, shadow_response

    def get_provider_info(self, provider_name: str) -> Optional[ChatProviderInfo]:
        """Get provider info."""
        provider = self._providers.get(provider_name)
        return provider.info if provider else None

    def list_providers(self) -> List[str]:
        """List available providers."""
        return [name for name, p in self._providers.items() if p.is_available()]


# Singleton
_router: Optional[ChatProviderRouter] = None


def get_chat_router() -> ChatProviderRouter:
    """Get global chat router instance."""
    global _router
    if _router is None:
        _router = ChatProviderRouter()
    return _router
