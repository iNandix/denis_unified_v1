"""Perplexity API client — search-oriented, OpenAI-compat format.

Uses the Perplexity sonar models for premium search with citations.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import aiohttp

from .gateway_types import ProviderCallResult
from .provider_adapter import ProviderAdapter


class PerplexityClient:
    """Low-level Perplexity API client."""

    provider = "perplexity"

    def __init__(self) -> None:
        self.api_key = (os.getenv("PERPLEXITY_API_KEY") or "").strip()
        self.endpoint = (
            os.getenv("DENIS_PERPLEXITY_URL")
            or "https://api.perplexity.ai/chat/completions"
        ).strip()
        self.model = (os.getenv("DENIS_PERPLEXITY_MODEL") or "sonar-pro").strip()
        self._cost_factor = float(os.getenv("DENIS_PERPLEXITY_COST_FACTOR", "0.80"))

    @property
    def cost_factor(self) -> float:
        return self._cost_factor

    def is_available(self) -> bool:
        return bool(self.api_key and self.endpoint)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float,
        **params: Any,
    ) -> Dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=max(0.5, timeout_sec))
        payload: Dict[str, Any] = {
            "model": params.pop("model", self.model),
            "messages": messages,
            "temperature": params.pop("temperature", 0.2),
            **params,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.endpoint, headers=headers, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f"perplexity_http_{resp.status}:{str(data)[:300]}")
                choices = data.get("choices") or []
                message = choices[0].get("message", {}) if choices else {}
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("perplexity_empty_response")
                usage = data.get("usage") or {}
                citations = data.get("citations") or []
                return {
                    "response": content.strip(),
                    "input_tokens": int(usage.get("prompt_tokens") or 0),
                    "output_tokens": int(usage.get("completion_tokens") or 0),
                    "citations": citations,
                    "raw": data,
                }


class PerplexitySearchAdapter(ProviderAdapter):
    """Search-oriented adapter wrapping PerplexityClient."""

    def __init__(self, client: Optional[PerplexityClient] = None) -> None:
        self._client = client or PerplexityClient()

    @property
    def provider_name(self) -> str:
        return "perplexity"

    def is_available(self) -> bool:
        return self._client.is_available()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self._client.cost_factor * (input_tokens + output_tokens) / 1000.0

    async def chat(
        self,
        messages: List[Dict[str, str]],
        timeout_sec: float = 10.0,
        **params: Any,
    ) -> ProviderCallResult:
        t0 = time.monotonic()
        try:
            result = await self._client.generate(messages, timeout_sec, **params)
            elapsed = (time.monotonic() - t0) * 1000
            inp = int(result.get("input_tokens") or 0)
            out = int(result.get("output_tokens") or 0)
            return ProviderCallResult(
                provider="perplexity",
                model=self._client.model,
                response=str(result.get("response") or ""),
                input_tokens=inp,
                output_tokens=out,
                latency_ms=elapsed,
                cost_usd_estimated=self._client.cost_factor * (inp + out) / 1000.0,
                raw=result.get("raw"),
                success=True,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return ProviderCallResult(
                provider="perplexity",
                model=self._client.model,
                error=str(exc),
                latency_ms=elapsed,
                success=False,
            )

    async def search(
        self,
        query: str,
        timeout_sec: float = 10.0,
        search_recency_filter: Optional[str] = None,
        search_domain_filter: Optional[List[str]] = None,
    ) -> ProviderCallResult:
        """Search-specific entry point with Perplexity search parameters."""
        messages = [{"role": "user", "content": query}]
        params: Dict[str, Any] = {}
        if search_recency_filter:
            params["search_recency_filter"] = search_recency_filter
        if search_domain_filter:
            params["search_domain_filter"] = search_domain_filter
        return await self.chat(messages, timeout_sec, **params)
