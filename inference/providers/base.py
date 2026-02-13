"""Base provider interface for inference engines."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, AsyncIterator, Optional
from dataclasses import dataclass


@dataclass
class ProviderMetadata:
    supports_stream: bool
    supports_tools: bool
    base_url: str
    cost: float
    provider: str
    model: str


class Provider(ABC):
    def __init__(self, engine_id: str, metadata: ProviderMetadata):
        self.engine_id = engine_id
        self.metadata = metadata

    @abstractmethod
    async def health(self) -> bool:
        """Check if provider is healthy."""
        pass

    @abstractmethod
    async def chat(
        self, messages: List[Dict[str, str]], stream: bool = False, **kwargs
    ) -> Dict[str, Any] | AsyncIterator[Dict[str, Any]]:
        """Execute chat completion."""
        pass

    async def safety(self, text: str) -> bool:
        """Check text safety. Override if provider supports it."""
        return True

    @property
    def is_available(self) -> bool:
        return True


class ProviderError(Exception):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass
