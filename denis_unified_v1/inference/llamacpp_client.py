"""Llama.cpp client for direct HTTP calls to local llama.cpp servers."""

from __future__ import annotations

import os
from typing import Any

import aiohttp

from denis_unified_v1.inference.hop import next_hop_header


class LlamaCppClient:
    provider = "llamacpp"

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._cost_factor = 0.0001

    @property
    def cost_factor(self) -> float:
        return self._cost_factor

    def is_available(self) -> bool:
        return bool(self.endpoint)

    async def generate(
        self,
        messages: list[dict[str, str]],
        timeout_sec: float,
        **params: Any,
    ) -> dict[str, Any]:
        url = self.endpoint
        if not url.endswith("/v1/chat/completions"):
            url = f"{url}/v1/chat/completions"

        payload: dict[str, Any] = {
            "model": "local",
            "messages": messages,
            "stream": False,
            **params,
        }

        timeout = aiohttp.ClientTimeout(total=max(0.5, timeout_sec))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Propagate hop counter to prevent Denis -> Denis loops when endpoints
            # are misconfigured to point back at this server.
            async with session.post(url, json=payload, headers=next_hop_header()) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f"llamacpp_http_{resp.status}:{str(data)[:300]}")

                choices = data.get("choices") or []
                msg = (choices[0].get("message") or {}) if choices else {}
                content = msg.get("content")

                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("llamacpp_empty_response")

                usage = data.get("usage") or {}
                return {
                    "response": content.strip(),
                    "input_tokens": int(usage.get("prompt_tokens") or 0),
                    "output_tokens": int(usage.get("completion_tokens") or 0),
                    "raw": data,
                }
