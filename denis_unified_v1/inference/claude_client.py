"""Anthropic Claude client."""

from __future__ import annotations

import os
from typing import Any

import aiohttp  # type: ignore[import-not-found]


def _to_anthropic_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role not in {"user", "assistant"}:
            role = "user"
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        out.append({"role": role, "content": content})
    return out or [{"role": "user", "content": "Hello"}]


class ClaudeClient:
    provider = "claude"

    def __init__(self) -> None:
        self.api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        self.endpoint = (
            os.getenv("DENIS_ANTHROPIC_URL") or "https://api.anthropic.com/v1/messages"
        ).strip()
        self.model = (
            os.getenv("DENIS_CLAUDE_MODEL") or "claude-3-5-sonnet-20241022"
        ).strip()
        self._cost_factor = float(os.getenv("DENIS_CLAUDE_COST_FACTOR", "0.45"))

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
            "messages": _to_anthropic_messages(messages),
            "max_tokens": int(os.getenv("DENIS_CLAUDE_MAX_TOKENS", "512")),
            "temperature": 0.2,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.endpoint, headers=headers, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f"claude_http_{resp.status}:{str(data)[:300]}")
                blocks = data.get("content") or []
                text = ""
                for block in blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text += str(block.get("text") or "")
                text = text.strip()
                if not text:
                    raise RuntimeError("claude_empty_response")
                usage = data.get("usage") or {}
                return {
                    "response": text,
                    "input_tokens": int(usage.get("input_tokens") or 0),
                    "output_tokens": int(usage.get("output_tokens") or 0),
                    "raw": data,
                }
