"""STT engine wrapper for Denis canonical STT service on port 8086."""

from __future__ import annotations

import base64
import os
from typing import Any

import aiohttp


class STTEngine:
    def __init__(self) -> None:
        self.base_url = (os.getenv("DENIS_STT_URL") or "http://127.0.0.1:8086").strip()
        self.timeout_sec = float(os.getenv("DENIS_STT_TIMEOUT_SEC", "4.0"))

    async def transcribe_base64(self, audio_base64: str, language: str = "es") -> dict[str, Any]:
        payload = {"audio_base64": audio_base64, "language": language}
        timeout = aiohttp.ClientTimeout(total=max(0.5, self.timeout_sec))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.base_url}/transcribe_base64", json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f"stt_http_{resp.status}:{str(data)[:300]}")
                text = str(data.get("text") or "").strip()
                return {
                    "text": text,
                    "raw": data,
                }

    async def transcribe_bytes(self, audio_bytes: bytes, language: str = "es") -> dict[str, Any]:
        encoded = base64.b64encode(audio_bytes).decode("ascii")
        return await self.transcribe_base64(encoded, language=language)
