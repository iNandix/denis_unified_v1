"""Audio stream framing helpers for websocket voice transport."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AudioChunk:
    seq: int
    audio_base64: str
    sample_rate_hz: int = 16000
    channels: int = 1
    format: str = "wav"

    def as_event(self) -> dict[str, Any]:
        return {
            "type": "audio_chunk",
            "seq": self.seq,
            "audio_base64": self.audio_base64,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "format": self.format,
            "timestamp_utc": _utc_now(),
        }


def bytes_to_base64(audio_bytes: bytes) -> str:
    return base64.b64encode(audio_bytes).decode("ascii")


def base64_to_bytes(audio_base64: str) -> bytes:
    return base64.b64decode(audio_base64.encode("ascii"))
