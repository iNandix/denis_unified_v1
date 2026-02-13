"""OpenAI-compatible provider."""

import os
from typing import Any, Dict, List, Optional
import httpx

from .base import Provider, ProviderMetadata, ProviderError
from ..engine_catalog import EngineSpec


class OpenAICompatProvider(Provider):
    def __init__(self, engine_spec: EngineSpec):
        if not engine_spec.base_url or not engine_spec.api_key:
            raise ValueError("OpenAI compat requires base_url and api_key")

        metadata = ProviderMetadata(
            supports_stream=True,
            supports_tools=True,
            base_url=engine_spec.base_url,
            cost=engine_spec.cost,
            provider="openai_compat",
            model=engine_spec.model,
        )
        super().__init__(engine_spec.id, metadata)
        self.engine_spec = engine_spec
        self.client = httpx.AsyncClient(
            timeout=engine_spec.timeout_ms / 1000,
            headers={"Authorization": f"Bearer {engine_spec.api_key}"},
        )

    async def health(self) -> bool:
        try:
            resp = await self.client.get(f"{self.engine_spec.base_url}/v1/models")
            return resp.status_code == 200
        except Exception:
            return False

    async def chat(
        self, messages: List[Dict[str, str]], stream: bool = False, **kwargs
    ) -> Dict[str, Any]:
        payload = {
            "model": self.engine_spec.model,
            "messages": messages,
            "stream": stream,
        }
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]

        try:
            resp = await self.client.post(
                f"{self.engine_spec.base_url}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise ProviderError(f"OpenAI compat error: {e}") from e

    async def close(self):
        await self.client.aclose()


def create_openai_provider(engine_spec: EngineSpec) -> Optional[OpenAICompatProvider]:
    if not engine_spec.base_url or not engine_spec.api_key:
        return None
    return OpenAICompatProvider(engine_spec)
