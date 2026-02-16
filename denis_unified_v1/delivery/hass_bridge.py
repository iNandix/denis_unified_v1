"""Optional Home Assistant bridge for voice output.

Converts PCM s16le streaming to WAV segments and plays via HA media_player.
Enabled by env DENIS_HASS_ENABLED=1.

Usage:
    bridge = HASSBridge()
    if bridge.enabled:
        await bridge.play_segment(pcm_bytes, request_id)
        await bridge.stop(request_id)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import wave
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

HA_BASE_URL = os.getenv("HA_BASE_URL") or os.getenv("HASS_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN") or os.getenv("HASS_TOKEN", "")
HA_MEDIA_PLAYER = os.getenv("HA_MEDIA_PLAYER", "media_player.salon")
SERVICE_PUBLIC_BASE_URL = os.getenv("SERVICE_PUBLIC_BASE_URL", "http://10.10.10.1:8084")
HASS_ENABLED = os.getenv("DENIS_HASS_ENABLED", "0") == "1"

SAMPLE_RATE = 22050
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit


class HASSBridge:
    """Bridge PCM audio to Home Assistant media_player."""

    def __init__(self):
        self.enabled = HASS_ENABLED and bool(HA_TOKEN)
        self._play_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=20)
        self._active_requests: set[str] = set()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {HA_TOKEN}",
            "Content-Type": "application/json",
        }

    def pcm_to_wav(self, pcm_bytes: bytes) -> bytes:
        """Convert raw PCM s16le to WAV."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm_bytes)
        return buf.getvalue()

    async def play_segment(
        self,
        pcm_bytes: bytes,
        request_id: str,
        segment_id: str = "",
    ) -> bool:
        """Convert PCM segment to WAV and play via HA media_player.

        Non-blocking: fires and forgets the REST call.
        """
        if not self.enabled:
            return False

        self._active_requests.add(request_id)
        wav_bytes = self.pcm_to_wav(pcm_bytes)

        # HA needs a URL to play. We serve the WAV from our own endpoint.
        # For simplicity, use play_media with a data URI or local file.
        # Best approach: POST to HA with media_content_id pointing to our service.
        media_url = (
            f"{SERVICE_PUBLIC_BASE_URL}/render/voice/segment"
            f"?request_id={request_id}&segment_id={segment_id}"
        )

        payload = {
            "entity_id": HA_MEDIA_PLAYER,
            "media_content_id": media_url,
            "media_content_type": "music",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{HA_BASE_URL}/api/services/media_player/play_media"
                async with session.post(
                    url, json=payload, headers=self._headers()
                ) as resp:
                    if resp.status < 400:
                        logger.info(f"HA play_media: {request_id}/{segment_id}")
                        return True
                    else:
                        text = await resp.text()
                        logger.warning(f"HA play_media failed {resp.status}: {text[:200]}")
        except Exception as e:
            logger.warning(f"HA play_media error: {e}")

        return False

    async def stop(self, request_id: str) -> bool:
        """Stop playback on HA media_player (barge-in)."""
        if not self.enabled:
            return False

        self._active_requests.discard(request_id)

        payload = {"entity_id": HA_MEDIA_PLAYER}

        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{HA_BASE_URL}/api/services/media_player/media_stop"
                async with session.post(
                    url, json=payload, headers=self._headers()
                ) as resp:
                    if resp.status < 400:
                        logger.info(f"HA media_stop: {request_id}")
                        return True
        except Exception as e:
            logger.warning(f"HA media_stop error: {e}")

        return False


# Singleton
_bridge: Optional[HASSBridge] = None


def get_hass_bridge() -> HASSBridge:
    global _bridge
    if _bridge is None:
        _bridge = HASSBridge()
    return _bridge
