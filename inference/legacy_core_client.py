"""Legacy Denis core client (default runtime at port 8084)."""

from __future__ import annotations

import os
from typing import Any

import aiohttp


class LegacyCoreClient:
    provider = "legacy_core"

    def __init__(self) -> None:
        self.endpoint = (
            os.getenv("DENIS_CORE_CHAT_URL")
            or os.getenv("DENIS_CORE_URL")
            or "http://127.0.0.1:8084/v1/chat"
        ).strip()
        self._cost_factor = float(os.getenv("DENIS_LEGACY_CORE_COST_FACTOR", "1.0"))

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
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = str(msg.get("content") or "").strip()
                if user_text:
                    break
        payload = {"message": user_text}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.endpoint, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(
                        f"legacy_core_http_{resp.status}:{str(data)[:300]}"
                    )
                text = ""
                if isinstance(data, dict):
                    for key in ("response", "answer", "text", "content"):
                        val = data.get(key)
                        if isinstance(val, str) and val.strip():
                            text = val.strip()
                            break
                if not text:
                    raise RuntimeError("legacy_core_empty_response")
                return {
                    "response": text,
                    "input_tokens": max(1, len(user_text.split())),
                    "output_tokens": max(1, len(text.split())),
                    "raw": data,
                }
