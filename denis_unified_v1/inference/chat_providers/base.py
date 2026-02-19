#!/usr/bin/env python3
"""
ChatProvider - Base interface for chat providers.

Unified contract for chat completions:
- Request: messages[], max_tokens, temperature, response_format, stream
- Response: text, json, provider, model, usage, latency_ms, error
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, AsyncIterator
import time


class ResponseFormat(str, Enum):
    TEXT = "text"
    JSON = "json"


@dataclass
class ChatRequest:
    """Chat request to provider."""

    messages: List[Dict[str, str]]
    max_tokens: int = 1024
    temperature: float = 0.7
    response_format: ResponseFormat = ResponseFormat.TEXT
    stream: bool = False


@dataclass
class Usage:
    """Token usage information."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatResponse:
    """Chat response from provider."""

    text: str = ""
    json: Optional[Dict[str, Any]] = None
    provider: str = ""
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    error: Optional[str] = None
    success: bool = True


@dataclass
class ChatProviderInfo:
    """Provider metadata."""

    provider: str
    model: str
    supports_stream: bool = False
    supports_json: bool = False
    base_url: str = ""
    cost_factor: float = 1.0


class ChatProvider(ABC):
    """Base class for chat providers."""

    def __init__(self):
        self._info: Optional[ChatProviderInfo] = None

    @property
    @abstractmethod
    def info(self) -> ChatProviderInfo:
        """Provider metadata."""
        pass

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Execute chat completion.

        Args:
            request: ChatRequest with messages and options

        Returns:
            ChatResponse with text/json, metadata, and telemetry
        """
        pass

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatResponse]:
        """
        Stream chat completion. Override if provider supports streaming.

        Yields:
            ChatResponse chunks
        """
        raise NotImplementedError(f"{self.info.provider} does not support streaming")

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass

    async def health(self) -> bool:
        """Check provider health."""
        return self.is_available()


class ChatProviderError(Exception):
    """Base error for chat providers."""

    pass


class ChatProviderTimeout(ChatProviderError):
    """Timeout error."""

    pass


class ChatProviderUnavailable(ChatProviderError):
    """Provider unavailable error."""

    pass


class ChatProviderRateLimit(ChatProviderError):
    """Rate limit error."""

    pass
