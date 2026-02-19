#!/usr/bin/env python3
"""
Anthropic Chat Adapter - Uses Messages API.

Implements ChatProvider interface for Anthropic Claude.
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
)

logger = logging.getLogger(__name__)


class AnthropicChatAdapter(ChatProvider):
    """Anthropic Claude chat provider using Messages API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
        self._base_url = (
            base_url
            or os.getenv("DENIS_ANTHROPIC_URL", "https://api.anthropic.com/v1").strip()
        )
        self._model = (
            model
            or os.getenv("DENIS_ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022").strip()
        )
        self._cost_factor = float(os.getenv("DENIS_ANTHROPIC_COST_FACTOR", "0.45"))
        self._timeout = float(os.getenv("DENIS_ANTHROPIC_TIMEOUT", "30"))

    @property
    def info(self) -> ChatProviderInfo:
        return ChatProviderInfo(
            provider="anthropic",
            model=self._model,
            supports_stream=False,
            supports_json=True,
            base_url=self._base_url,
            cost_factor=self._cost_factor,
        )

    def is_available(self) -> bool:
        return bool(self._api_key and self._base_url)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion via Anthropic Messages API."""
        start = time.time()

        if not self.is_available():
            return ChatResponse(
                provider="anthropic",
                model=self._model,
                error="Anthropic API key not configured",
                success=False,
            )

        url = f"{self._base_url}/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        system = None
        messages = []
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system = content
            elif role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

        if not messages:
            messages = [{"role": "user", "content": "Hello"}]

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if system:
            payload["system"] = system

        if request.response_format == ResponseFormat.JSON:
            payload["system"] = (
                payload.get("system") or ""
            ) + "\n\nRespond only in valid JSON format."

        timeout = aiohttp.ClientTimeout(total=self._timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    latency = int((time.time() - start) * 1000)

                    if resp.status == 429:
                        return ChatResponse(
                            provider="anthropic",
                            model=self._model,
                            error="rate_limit_exceeded",
                            latency_ms=latency,
                            success=False,
                        )

                    if resp.status >= 500:
                        return ChatResponse(
                            provider="anthropic",
                            model=self._model,
                            error="provider_error",
                            latency_ms=latency,
                            success=False,
                        )

                    if resp.status != 200:
                        text = await resp.text()
                        return ChatResponse(
                            provider="anthropic",
                            model=self._model,
                            error=f"http_error_{resp.status}: {text[:200]}",
                            latency_ms=latency,
                            success=False,
                        )

                    data = await resp.json()
                    return self._parse_response(data, latency, request.response_format)

        except TimeoutError:
            latency = int((time.time() - start) * 1000)
            return ChatResponse(
                provider="anthropic",
                model=self._model,
                error="timeout",
                latency_ms=latency,
                success=False,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            logger.warning(f"Anthropic chat error: {e}")
            return ChatResponse(
                provider="anthropic",
                model=self._model,
                error=str(e)[:100],
                latency_ms=latency,
                success=False,
            )

    def _parse_response(
        self,
        data: Dict[str, Any],
        latency: int,
        response_format: ResponseFormat = ResponseFormat.TEXT,
    ) -> ChatResponse:
        """Parse Anthropic Messages API response."""
        try:
            content_blocks = data.get("content", [])
            text_content = ""
            json_data = None

            for block in content_blocks:
                if block.get("type") == "text":
                    text_content = block.get("text", "")

                    if response_format == ResponseFormat.JSON:
                        try:
                            json_data = json.loads(text_content.strip())
                        except json.JSONDecodeError:
                            pass

            usage_data = data.get("usage", {})

            return ChatResponse(
                text=text_content,
                json=json_data,
                provider="anthropic",
                model=self._model,
                usage=Usage(
                    input_tokens=usage_data.get("input_tokens", 0),
                    output_tokens=usage_data.get("output_tokens", 0),
                    total_tokens=usage_data.get("usage_tokens", 0),
                ),
                latency_ms=latency,
                success=True,
            )

        except Exception as e:
            return ChatResponse(
                provider="anthropic",
                model=self._model,
                error=f"parse_error: {e}",
                latency_ms=latency,
                success=False,
            )
