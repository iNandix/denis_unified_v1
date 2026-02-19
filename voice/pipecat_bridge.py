"""WS12-G Pipecat bridge helpers (graph-first voice session ids).

This module is intentionally small and dependency-light:
- It must be importable even when Pipecat is not installed.
- It must never require secrets.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any


def new_voice_session_id(*, conversation_id: str, session_ts_ms: int) -> str:
    """Stable VoiceSession id per (conversation_id, session_ts_ms).

    Spec:
      id = sha256(conversation_id + ":" + session_ts)
    """
    conv = (conversation_id or "").strip() or "default"
    raw = f"{conv}:{int(session_ts_ms)}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _pipecat_base_url() -> str:
    return (os.getenv("PIPECAT_BASE_URL") or "http://127.0.0.1:8004").strip().rstrip("/")


async def pipecat_stt_transcribe(
    *,
    audio_base64: str,
    language: str = "es",
    timeout_sec: float | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """One-shot STT via Pipecat canonical service (/v1/stt).

    Fail-open at callsites: this helper raises on HTTP or decode errors.
    """
    url = f"{(base_url or _pipecat_base_url()).rstrip('/')}/v1/stt"
    timeout_total = float(timeout_sec if timeout_sec is not None else os.getenv("PIPECAT_STT_TIMEOUT_SEC", "6.0"))
    timeout_total = max(0.5, timeout_total)

    try:
        import aiohttp
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"pipecat_stt_no_aiohttp:{type(exc).__name__}") from exc

    timeout = aiohttp.ClientTimeout(total=timeout_total)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            url,
            json={"audio_base64": str(audio_base64 or ""), "language": str(language or "es")},
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(f"pipecat_stt_http_{resp.status}:{body[:200]}")
            data = await resp.json(content_type=None)
            if not isinstance(data, dict):
                raise RuntimeError("pipecat_stt_bad_response")
            return data
