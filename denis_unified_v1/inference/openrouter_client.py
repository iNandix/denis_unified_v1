"""OpenRouter chat client."""

from __future__ import annotations

import os
from typing import Any

import aiohttp  # type: ignore[import-not-found]


class OpenRouterClient:
    provider = "openrouter"

    def __init__(self) -> None:
        self.api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        self.endpoint = (
            os.getenv("DENIS_OPENROUTER_URL")
            or "https://openrouter.ai/api/v1/chat/completions"
        ).strip()
        self.model = (os.getenv("DENIS_OPENROUTER_MODEL") or "openai/gpt-4o-mini").strip()
        self.site_url = (os.getenv("DENIS_OPENROUTER_SITE_URL") or "").strip()
        self.site_name = (os.getenv("DENIS_OPENROUTER_SITE_NAME") or "denis-unified-v1").strip()
        self._cost_factor = float(os.getenv("DENIS_OPENROUTER_COST_FACTOR", "0.65"))

    @property
    def cost_factor(self) -> float:
        return self._cost_factor

    def is_available(self) -> bool:
        return bool(self.api_key and self.endpoint)

    async def generate(
        self,
        messages: list[dict[str, str]],
        timeout_sec: float,
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=max(0.5, timeout_sec))
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            headers["X-Title"] = self.site_name
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.endpoint, headers=headers, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(
                        f"openrouter_http_{resp.status}:{str(data)[:300]}"
                    )
                choices = data.get("choices") or []
                message = choices[0].get("message", {}) if choices else {}
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("openrouter_empty_response")
                usage = data.get("usage") or {}
                return {
                    "response": content.strip(),
                    "input_tokens": int(usage.get("prompt_tokens") or 0),
                    "output_tokens": int(usage.get("completion_tokens") or 0),
                    "raw": data,
                }
