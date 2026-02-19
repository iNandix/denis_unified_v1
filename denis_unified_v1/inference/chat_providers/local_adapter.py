#!/usr/bin/env python3
"""
Local Chat Adapter - Fallback stub for local inference.

Implements ChatProvider interface for local models (llamacpp, etc.).
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

from .base import (
    ChatProvider,
    ChatProviderInfo,
    ChatRequest,
    ChatResponse,
    Usage,
)

logger = logging.getLogger(__name__)


class LocalChatAdapter(ChatProvider):
    """Local chat provider fallback using llamacpp or similar."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._endpoint = (
            endpoint
            or os.getenv(
                "DENIS_LOCAL_CHAT_URL", "http://localhost:8080/v1/chat/completions"
            ).strip()
        )
        self._model = model or os.getenv("DENIS_LOCAL_CHAT_MODEL", "qwen2.5-3b").strip()
        self._cost_factor = 0.0  # Free local inference
        self._timeout = float(os.getenv("DENIS_LOCAL_CHAT_TIMEOUT", "60"))

    @property
    def info(self) -> ChatProviderInfo:
        return ChatProviderInfo(
            provider="local",
            model=self._model,
            supports_stream=False,
            supports_json=False,
            base_url=self._endpoint,
            cost_factor=self._cost_factor,
        )

    def is_available(self) -> bool:
        return bool(self._endpoint)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion via local endpoint."""
        start = time.time()

        if not self.is_available():
            return ChatResponse(
                provider="local",
                model=self._model,
                error="Local endpoint not configured",
                success=False,
            )

        import aiohttp

        headers = {"Content-Type": "application/json"}
        payload = {
            "model": self._model,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        timeout = aiohttp.ClientTimeout(total=self._timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self._endpoint, json=payload, headers=headers
                ) as resp:
                    latency = int((time.time() - start) * 1000)

                    if resp.status != 200:
                        text = await resp.text()
                        return ChatResponse(
                            provider="local",
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
                provider="local",
                model=self._model,
                error="timeout",
                latency_ms=latency,
                success=False,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            logger.warning(f"Local chat error: {e}")
            return ChatResponse(
                provider="local",
                model=self._model,
                error=str(e)[:100],
                latency_ms=latency,
                success=False,
            )

    def _parse_response(self, data: Dict[str, Any], latency: int) -> ChatResponse:
        """Parse local chat response."""
        try:
            choices = data.get("choices", [])
            text_content = ""

            if choices:
                message = choices[0].get("message", {})
                text_content = message.get("content", "")

            usage_data = data.get("usage", {})

            return ChatResponse(
                text=text_content,
                provider="local",
                model=self._model,
                usage=Usage(
                    input_tokens=usage_data.get("prompt_tokens", 0),
                    output_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                ),
                latency_ms=latency,
                success=True,
            )

        except Exception as e:
            return ChatResponse(
                provider="local",
                model=self._model,
                error=f"parse_error: {e}",
                latency_ms=latency,
                success=False,
            )
