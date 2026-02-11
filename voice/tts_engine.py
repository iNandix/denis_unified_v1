"""TTS engine wrapper with primary and fallback endpoints."""

from __future__ import annotations

import base64
import os
from typing import Any

import aiohttp


class TTSEngine:
    def __init__(self) -> None:
        self.primary_url = (
            os.getenv("DENIS_TTS_URL") or "http://127.0.0.1:8084/v1/voice/tts"
        ).strip()
        self.fallback_url = (
            os.getenv("DENIS_TTS_FALLBACK_URL") or "http://10.10.10.2:5002/api/tts"
        ).strip()
        self.timeout_sec = float(os.getenv("DENIS_TTS_TIMEOUT_SEC", "6.0"))

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str = "es",
    ) -> dict[str, Any]:
        if not text.strip():
            return {"audio_base64": "", "bytes_len": 0, "provider": "none"}

        payload_primary: dict[str, Any] = {
            "text": text,
            "voice": voice or os.getenv("DENIS_TTS_VOICE", "es-ES-female"),
            "language": language,
            "format": "wav",
        }
        timeout = aiohttp.ClientTimeout(total=max(0.5, self.timeout_sec))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.primary_url, json=payload_primary) as resp:
                    if resp.status < 400:
                        content_type = (resp.headers.get("content-type") or "").lower()
                        if "application/json" in content_type:
                            data = await resp.json(content_type=None)
                            audio_b64 = str(data.get("audio_base64") or "").strip() if isinstance(data, dict) else ""
                            if audio_b64:
                                return {
                                    "audio_base64": audio_b64,
                                    "bytes_len": len(base64.b64decode(audio_b64.encode("ascii"))),
                                    "provider": "primary_json",
                                }
                            raise RuntimeError(f"tts_primary_json_without_audio:{str(data)[:200]}")

                        body = await resp.read()
                        if not body:
                            raise RuntimeError("tts_primary_empty_body")
                        audio_b64 = base64.b64encode(body).decode("ascii")
                        return {
                            "audio_base64": audio_b64,
                            "bytes_len": len(body),
                            "provider": "primary",
                        }
        except Exception:
            pass

        payload_fallback = {
            "text": text,
            "speaker_id": os.getenv("DENIS_TTS_SPEAKER_ID", "es_male"),
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.fallback_url, json=payload_fallback) as resp:
                    if resp.status >= 400:
                        data = await resp.text()
                        raise RuntimeError(f"tts_fallback_http_{resp.status}:{data[:300]}")
                    body = await resp.read()
                    if not body:
                        raise RuntimeError("tts_fallback_empty_body")
                    audio_b64 = base64.b64encode(body).decode("ascii")
                    return {
                        "audio_base64": audio_b64,
                        "bytes_len": len(body),
                        "provider": "fallback",
                    }
        except Exception as exc:
            return {
                "audio_base64": "",
                "bytes_len": 0,
                "provider": "unavailable",
                "error": str(exc)[:300],
            }
