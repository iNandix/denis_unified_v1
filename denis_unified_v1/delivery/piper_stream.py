"""Piper TTS streaming provider for real-time voice synthesis.

Supports:
- /synthesize_stream: streaming PCM chunks with low TTFC
- /synthesize: fallback to WAV for full synthesis
- Interrupt/cancel: stops stream on demand
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import AsyncIterator, Optional

import aiohttp


class PiperStreamProvider:
    """Streaming TTS provider using Piper HTTP API."""

    def __init__(
        self,
        base_url: str = "http://10.10.10.2:8005",
        sample_rate: int = 22050,
        encoding: str = "pcm_s16le",
        voice: str = "es_ES-davefx-medium",
    ):
        self.base_url = base_url
        self.sample_rate = sample_rate
        self.encoding = encoding
        self.voice = voice

    async def synthesize_stream(
        self,
        text: str,
        request_id: str,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[dict]:
        """Stream audio chunks from Piper."""
        url = f"{self.base_url}/synthesize_stream"

        payload = {
            "text": text,
            "voice": self.voice,
            "encoding": self.encoding,
            "sample_rate": self.sample_rate,
        }

        session_timeout = aiohttp.ClientTimeout(total=30, connect=5)

        try:
            async with aiohttp.ClientSession(timeout=session_timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        # Fallback to non-streaming
                        async for chunk in self._fallback_synthesize(
                            text, request_id, cancel_event
                        ):
                            yield chunk
                        return

                    bytes_received = 0
                    start_ts = time.time()
                    sequence = 0
                    accumulated_ms = 0

                    async for chunk in response.content.iter_chunked(1024):
                        if cancel_event and cancel_event.is_set():
                            break

                        if len(chunk) > 0:
                            bytes_received += len(chunk)
                            # Estimate duration: chunk_size / (sample_rate * channels * bytes_per_sample)
                            chunk_duration_ms = (
                                len(chunk) / (self.sample_rate * 1 * 2)
                            ) * 1000
                            accumulated_ms += chunk_duration_ms

                            yield {
                                "request_id": request_id,
                                "type": "render.voice.delta",
                                "sequence": sequence,
                                "payload": {
                                    "stream_id": request_id,
                                    "encoding": self.encoding,
                                    "sample_rate": self.sample_rate,
                                    "channels": 1,
                                    "pts_ms": int(accumulated_ms),
                                    "audio_b64": base64.b64encode(chunk).decode(
                                        "utf-8"
                                    ),
                                },
                                "ts": time.time(),
                            }
                            sequence += 1

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Piper stream error: {e}")
            # Fallback to non-streaming
            async for chunk in self._fallback_synthesize(
                text, request_id, cancel_event
            ):
                yield chunk

    async def _fallback_synthesize(
        self,
        text: str,
        request_id: str,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[dict]:
        """Fallback: single WAV response, chunked for streaming simulation."""
        url = f"{self.base_url}/synthesize"

        payload = {
            "text": text,
            "voice": self.voice,
        }

        session_timeout = aiohttp.ClientTimeout(total=30, connect=5)

        try:
            async with aiohttp.ClientSession(timeout=session_timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        return

                    audio_bytes = await response.read()
                    bytes_received = len(audio_bytes)

                    # Simple WAV parsing - assume standard WAV header (44 bytes)
                    # Then chunk the PCM data
                    WAV_HEADER_SIZE = 44
                    chunk_size = 2048  # ~46ms at 22050Hz

                    if audio_bytes[:4] != b"RIFF":
                        # Not a WAV, yield as single chunk
                        yield {
                            "request_id": request_id,
                            "type": "render.voice.delta",
                            "sequence": 0,
                            "payload": {
                                "stream_id": request_id,
                                "encoding": "wav",
                                "sample_rate": self.sample_rate,
                                "channels": 1,
                                "pts_ms": 0,
                                "audio_b64": base64.b64encode(audio_bytes).decode(
                                    "utf-8"
                                ),
                            },
                            "ts": time.time(),
                        }
                        return

                    # Extract PCM data after header
                    pcm_data = audio_bytes[WAV_HEADER_SIZE:]
                    sequence = 0
                    accumulated_ms = 0

                    for i in range(0, len(pcm_data), chunk_size):
                        if cancel_event and cancel_event.is_set():
                            break

                        chunk = pcm_data[i : i + chunk_size]
                        if len(chunk) == 0:
                            continue

                        chunk_duration_ms = (
                            len(chunk) / (self.sample_rate * 1 * 2)
                        ) * 1000
                        accumulated_ms += chunk_duration_ms

                        yield {
                            "request_id": request_id,
                            "type": "render.voice.delta",
                            "sequence": sequence,
                            "payload": {
                                "stream_id": request_id,
                                "encoding": "pcm_s16le",
                                "sample_rate": self.sample_rate,
                                "channels": 1,
                                "pts_ms": int(accumulated_ms),
                                "audio_b64": base64.b64encode(chunk).decode("utf-8"),
                            },
                            "ts": time.time(),
                        }
                        sequence += 1
                        # Small delay to simulate streaming
                        await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Piper fallback error: {e}")


def get_piper_provider(
    base_url: str = "http://10.10.10.2:8005",
    sample_rate: int = 22050,
) -> PiperStreamProvider:
    """Get a Piper streaming provider instance."""
    return PiperStreamProvider(
        base_url=base_url,
        sample_rate=sample_rate,
    )


class PiperCancelMixin:
    """Mixin to add cancel capability to Piper provider."""

    async def cancel_request(self, request_id: str) -> bool:
        """Cancel an active stream request."""
        import aiohttp

        base_url = getattr(self, "base_url", None)
        if not base_url:
            return False
        url = f"{base_url}/cancel"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"request_id": request_id}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("was_active", False)
        except Exception as e:
            print(f"Piper cancel error: {e}")
        return False


class PiperStreamProviderWithCancel(PiperCancelMixin, PiperStreamProvider):
    """Piper provider with cancel support."""

    pass
