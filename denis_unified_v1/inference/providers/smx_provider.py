"""SMX Provider - calls to local SMX engines."""

import asyncio
import time
from typing import Any, Dict, List, Optional
import httpx

from .base import (
    Provider,
    ProviderMetadata,
    ProviderError,
)
from ..engine_catalog import EngineSpec


class SMXProvider(Provider):
    def __init__(self, engine_spec: EngineSpec):
        metadata = ProviderMetadata(
            supports_stream=False,
            supports_tools=False,
            base_url=engine_spec.base_url,
            cost=engine_spec.cost,
            provider="smx",
            model=engine_spec.model,
        )
        super().__init__(engine_spec.id, metadata)
        self.engine_spec = engine_spec
        self.client = httpx.AsyncClient(timeout=engine_spec.timeout_ms / 1000)
        self._health_cache: Optional[tuple[bool, float]] = None

    async def health(self) -> bool:
        now = time.time()
        if self._health_cache:
            cached_health, cached_time = self._health_cache
            if now - cached_time < 2.0:
                return cached_health

        try:
            resp = await self.client.get(f"{self.engine_spec.base_url}/health")
            is_healthy = resp.status_code == 200
        except Exception:
            is_healthy = False

        self._health_cache = (is_healthy, now)
        return is_healthy

    async def chat(
        self, messages: List[Dict[str, str]], stream: bool = False, **kwargs
    ) -> Dict[str, Any] | Any:
        payload = {
            "messages": messages,
            "stream": stream,
        }
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]

        try:
            resp = await self.client.post(
                f"{self.engine_spec.base_url}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()

            if stream:
                return resp.iter_lines()
            return resp.json()
        except httpx.TimeoutException as e:
            raise ProviderError(f"Timeout calling {self.engine_id}") from e
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"HTTP error calling {self.engine_id}: {e}") from e

    async def safety(self, text: str) -> bool:
        if self.engine_spec.id != "smx_safety":
            return True

        try:
            resp = await self.client.post(
                f"{self.engine_spec.base_url}/v1/safety/check",
                json={"text": text},
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get("safe", True)
        except Exception:
            pass
        return True

    async def close(self):
        await self.client.aclose()


def create_smx_provider(engine_spec: EngineSpec) -> SMXProvider:
    return SMXProvider(engine_spec)
