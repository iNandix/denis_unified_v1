"""Legacy Denis core client (default runtime at port 8084)."""

from __future__ import annotations

import os
from typing import Any

import aiohttp  # type: ignore[import-not-found]


class LegacyCoreClient:
    provider = "legacy_core"

    def __init__(self) -> None:
        self.endpoint = (
            os.getenv("DENIS_CORE_CHAT_URL")
            or os.getenv("DENIS_CORE_URL")
            or "http://127.0.0.1:8084/v1/chat/completions"
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
        raw = (self.endpoint or "").strip()
        if not raw:
            raise RuntimeError("legacy_core_missing_endpoint")

        endpoint = raw.rstrip("/")
        if not endpoint.endswith("/v1/chat") and not endpoint.endswith("/v1/chat/completions"):
            endpoint = f"{endpoint}/v1/chat/completions"

        candidates: list[tuple[str, str]] = []
        if endpoint.endswith("/v1/chat/completions"):
            base = endpoint[: -len("/v1/chat/completions")]
            candidates = [
                ("openai", endpoint),
                ("legacy", f"{base}/v1/chat"),
            ]
        elif endpoint.endswith("/v1/chat"):
            base = endpoint[: -len("/v1/chat")]
            candidates = [
                ("legacy", endpoint),
                ("openai", f"{base}/v1/chat/completions"),
            ]
        else:
            candidates = [("openai", endpoint)]

        async with aiohttp.ClientSession(timeout=timeout) as session:
            last_err = "legacy_core_no_attempt"
            for kind, url in candidates:
                if kind == "legacy":
                    payload: dict[str, Any] = {"message": user_text}
                else:
                    payload = {
                        "model": os.getenv("DENIS_CORE_MODEL", "denis-cognitive"),
                        "messages": [{"role": "user", "content": user_text}],
                        "stream": False,
                    }

                async with session.post(url, json=payload) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status >= 400:
                        last_err = f"legacy_core_http_{resp.status}:{str(data)[:300]}"
                        continue

                    text = ""
                    if kind == "openai" and isinstance(data, dict):
                        choices = data.get("choices")
                        if isinstance(choices, list) and choices:
                            choice_msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                            if isinstance(choice_msg, dict):
                                content = choice_msg.get("content")
                                if isinstance(content, str) and content.strip():
                                    text = content.strip()

                    if kind == "legacy" and isinstance(data, dict):
                        for key in ("response", "answer", "text", "content"):
                            val = data.get(key)
                            if isinstance(val, str) and val.strip():
                                text = val.strip()
                                break

                    if text:
                        return {
                            "response": text,
                            "input_tokens": max(1, len(user_text.split())),
                            "output_tokens": max(1, len(text.split())),
                            "raw": data,
                        }

            raise RuntimeError(last_err or "legacy_core_empty_response")
