"""In-memory cache for voice segments (PCM) to serve via HASS."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class VoiceSegment:
    """Cached voice segment."""

    request_id: str
    segment_id: str
    sample_rate: int = 22050
    channels: int = 1
    encoding: str = "pcm_s16le"
    pcm_bytes: bytes = b""
    created_at: float = field(default_factory=time.time)
    is_complete: bool = False
    is_cancelled: bool = False


class VoiceSegmentCache:
    """In-memory cache for voice segments (request_id -> segment_id -> VoiceSegment)."""

    def __init__(self, max_segments: int = 100):
        self._cache: Dict[str, Dict[str, VoiceSegment]] = {}
        self._max_segments = max_segments
        self._lock = asyncio.Lock()

    def _make_key(self, request_id: str, segment_id: str) -> str:
        return f"{request_id}:{segment_id}"

    async def start_segment(
        self,
        request_id: str,
        segment_id: str,
        sample_rate: int = 22050,
        channels: int = 1,
        encoding: str = "pcm_s16le",
    ) -> VoiceSegment:
        """Start a new segment (call when first chunk arrives)."""
        async with self._lock:
            if request_id not in self._cache:
                self._cache[request_id] = {}
                # Evict old requests if cache full
                if len(self._cache) > self._max_segments:
                    oldest = min(
                        self._cache.keys(), key=lambda k: self._cache[k].get("_ts", 0)
                    )
                    del self._cache[oldest]

            seg = VoiceSegment(
                request_id=request_id,
                segment_id=segment_id,
                sample_rate=sample_rate,
                channels=channels,
                encoding=encoding,
            )
            self._cache[request_id][segment_id] = seg
            return seg

    async def append_audio(
        self,
        request_id: str,
        segment_id: str,
        pcm_chunk: bytes,
    ) -> Optional[VoiceSegment]:
        """Append PCM chunk to segment."""
        async with self._lock:
            if request_id not in self._cache:
                return None
            seg = self._cache[request_id].get(segment_id)
            if seg:
                seg.pcm_bytes += pcm_chunk
            return seg

    async def complete_segment(self, request_id: str, segment_id: str) -> bool:
        """Mark segment as complete."""
        async with self._lock:
            if request_id not in self._cache:
                return False
            seg = self._cache[request_id].get(segment_id)
            if seg:
                seg.is_complete = True
                return True
            return False

    async def cancel_request(self, request_id: str) -> bool:
        """Mark all segments for request as cancelled."""
        async with self._lock:
            if request_id not in self._cache:
                return False
            for seg in self._cache[request_id].values():
                seg.is_cancelled = True
            return True

    async def get_segment(
        self,
        request_id: str,
        segment_id: str,
    ) -> Optional[VoiceSegment]:
        """Get segment by request_id + segment_id."""
        async with self._lock:
            if request_id not in self._cache:
                return None
            return self._cache[request_id].get(segment_id)

    async def get_latest_segment(self, request_id: str) -> Optional[VoiceSegment]:
        """Get the most recent complete segment for a request."""
        async with self._lock:
            if request_id not in self._cache:
                return None
            segments = self._cache[request_id]
            # Get last complete segment
            complete = [s for s in segments.values() if s.is_complete]
            if complete:
                return max(complete, key=lambda s: s.created_at)
            return None


# Global cache instance
_voice_cache: Optional[VoiceSegmentCache] = None


def get_voice_cache() -> VoiceSegmentCache:
    global _voice_cache
    if _voice_cache is None:
        _voice_cache = VoiceSegmentCache()
    return _voice_cache
