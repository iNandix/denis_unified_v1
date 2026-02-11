"""vLLM OpenAI-compatible client."""

from __future__ import annotations

import os
from typing import Any

import aiohttp


class VLLMClient:
    provider = "vllm"

    def __init__(self) -> None:
        self.endpoint = (
            os.getenv("DENIS_VLLM_URL") or "http://10.10.10.2:9999/v1/chat/completions"
        ).strip()
        self.model = (os.getenv("DENIS_VLLM_MODEL") or "deepseek-coder").strip()
        self.api_key = (os.getenv("DENIS_VLLM_API_KEY") or "").strip()
        self._cost_factor = float(os.getenv("DENIS_VLLM_COST_FACTOR", "0.95"))

    @property
    def cost_factor(self) -> float:
        return self._cost_factor

    def is_available(self) -> bool:
        return bool(self.endpoint)

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
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.endpoint, headers=headers, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f"vllm_http_{resp.status}:{str(data)[:300]}")
                choices = data.get("choices") or []
                message = choices[0].get("message", {}) if choices else {}
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("vllm_empty_response")
                usage = data.get("usage") or {}
                return {
                    "response": content.strip(),
                    "input_tokens": int(usage.get("prompt_tokens") or 0),
                    "output_tokens": int(usage.get("completion_tokens") or 0),
                    "raw": data,
                }
