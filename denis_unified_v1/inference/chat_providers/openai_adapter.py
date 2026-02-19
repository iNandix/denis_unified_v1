#!/usr/bin/env python3
"""
OpenAI Chat Adapter - Uses Responses API (2024-12-01-preview).

Implements ChatProvider interface for OpenAI.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import aiohttp

from .base import (
    ChatProvider,
    ChatProviderInfo,
    ChatRequest,
    ChatResponse,
    ResponseFormat,
    Usage,
    ChatProviderError,
    ChatProviderTimeout,
    ChatProviderUnavailable,
)

logger = logging.getLogger(__name__)


class OpenAIChatAdapter(ChatProvider):
    """OpenAI chat provider using Responses API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
        self._base_url = (
            base_url
            or os.getenv("DENIS_OPENAI_URL", "https://api.openai.com/v1").strip()
        )
        self._model = model or os.getenv("DENIS_OPENAI_MODEL", "gpt-4o-mini").strip()
        self._cost_factor = float(os.getenv("DENIS_OPENAI_COST_FACTOR", "0.15"))
        self._timeout = float(os.getenv("DENIS_OPENAI_TIMEOUT", "30"))

    @property
    def info(self) -> ChatProviderInfo:
        return ChatProviderInfo(
            provider="openai",
            model=self._model,
            supports_stream=False,
            supports_json=True,
            base_url=self._base_url,
            cost_factor=self._cost_factor,
        )

    def is_available(self) -> bool:
        return bool(self._api_key and self._base_url)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion via OpenAI Responses API."""
        start = time.time()

        if not self.is_available():
            return ChatResponse(
                provider="openai",
                model=self._model,
                error="OpenAI API key not configured",
                success=False,
            )

        url = f"{self._base_url}/responses"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self._model,
            "input": self._format_messages(request.messages),
            "max_output_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if request.response_format == ResponseFormat.JSON:
            payload["text"] = {"format": {"type": "json_object"}}

        timeout = aiohttp.ClientTimeout(total=self._timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    latency = int((time.time() - start) * 1000)

                    if resp.status == 429:
                        return ChatResponse(
                            provider="openai",
                            model=self._model,
                            error="rate_limit_exceeded",
                            latency_ms=latency,
                            success=False,
                        )

                    if resp.status >= 500:
                        return ChatResponse(
                            provider="openai",
                            model=self._model,
                            error="provider_error",
                            latency_ms=latency,
                            success=False,
                        )

                    if resp.status != 200:
                        text = await resp.text()
                        return ChatResponse(
                            provider="openai",
                            model=self._model,
                            error=f"http_error_{resp.status}: {text[:200]}",
                            latency_ms=latency,
                            success=False,
                        )

                    data = await resp.json()
                    return self._parse_response(data, latency)

        except TimeoutError:
            latency = int((time.time() - start) * 1000)
            return ChatResponse(
                provider="openai",
                model=self._model,
                error="timeout",
                latency_ms=latency,
                success=False,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            logger.warning(f"OpenAI chat error: {e}")
            return ChatResponse(
                provider="openai",
                model=self._model,
                error=str(e)[:100],
                latency_ms=latency,
                success=False,
            )

    def _format_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Format messages for Responses API."""
        return [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
        ]

    def _parse_response(self, data: Dict[str, Any], latency: int) -> ChatResponse:
        """Parse OpenAI Responses API response."""
        try:
            output = data.get("output", [])
            text_content = ""
            json_data = None

            for item in output:
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            text_content = content.get("text", "")

                            if text_content.startswith("```json"):
                                text_content = text_content[7:]
                            if text_content.endswith("```"):
                                text_content = text_content[:-3]

                            try:
                                json_data = json.loads(text_content.strip())
                            except json.JSONDecodeError:
                                pass

            usage_data = data.get("usage", {})

            return ChatResponse(
                text=text_content,
                json=json_data,
                provider="openai",
                model=self._model,
                usage=Usage(
                    input_tokens=usage_data.get("input_tokens", 0),
                    output_tokens=usage_data.get("output_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                ),
                latency_ms=latency,
                success=True,
            )

        except Exception as e:
            return ChatResponse(
                provider="openai",
                model=self._model,
                error=f"parse_error: {e}",
                latency_ms=latency,
                success=False,
            )
