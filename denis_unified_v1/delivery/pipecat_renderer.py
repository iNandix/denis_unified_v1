import asyncio
import base64
import re
import time
from typing import Callable, Dict, Any, Optional, Literal, AsyncIterator

from .events_v1 import *
from .piper_stream import PiperStreamProvider, PiperStreamProviderWithCancel
from .voice_cache import get_voice_cache


class VoiceMetrics:
    """Metrics for voice synthesis."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.request_start_ts: Optional[float] = None  # When request arrived
        self.tts_start_ts: Optional[float] = None  # When first segment started
        self.tts_first_chunk_ts: Optional[float] = (
            None  # When first audio chunk arrived
        )
        self.tts_end_ts: Optional[float] = None
        self.bytes_streamed: int = 0
        self.chunks_count: int = 0
        self.cancelled: bool = False
        self.cancel_ts: Optional[float] = None
        self.backend: str = "none"

    def to_dict(self) -> dict:
        # TTFC global: from request_start to first audio chunk
        voice_ttfc_ns = 0
        if self.request_start_ts and self.tts_first_chunk_ts:
            voice_ttfc_ns = int(
                (self.tts_first_chunk_ts - self.request_start_ts) * 1_000_000_000
            )
        # Fallback to segment-level TTFC if global not available
        elif self.tts_start_ts and self.tts_first_chunk_ts:
            voice_ttfc_ns = int(
                (self.tts_first_chunk_ts - self.tts_start_ts) * 1_000_000_000
            )

        audio_duration_ms = 0
        if self.tts_end_ts and self.request_start_ts:
            audio_duration_ms = int((self.tts_end_ts - self.request_start_ts) * 1000)
        elif self.tts_end_ts and self.tts_start_ts:
            audio_duration_ms = int((self.tts_end_ts - self.tts_start_ts) * 1000)

        cancel_latency_ms = 0
        if self.cancel_ts and self.tts_end_ts:
            cancel_latency_ms = int((self.cancel_ts - self.tts_end_ts) * 1000)

        return {
            "voice_ttfc_ns": voice_ttfc_ns,
            "voice_ttfc_ms": int(voice_ttfc_ns / 1_000_000),
            "tts_backend": self.backend,
            "voice_cancelled": self.cancelled,
            "cancel_latency_ms": cancel_latency_ms,
            "bytes_streamed": self.bytes_streamed,
            "audio_duration_ms": audio_duration_ms,
            "chunks_count": self.chunks_count,
        }


class PipecatRendererNode:
    def __init__(
        self,
        emit_callback: Callable[[Dict[str, Any]], None],
        voice_enabled: bool = False,
        tts_provider: Literal["none", "piper_http", "piper_stream"] = "none",
        piper_base_url: Optional[str] = "http://10.10.10.2:8005",
        sample_rate: int = 22050,
        chunk_chars: int = 160,
        segment_chars: int = 140,
    ):
        self.emit_callback = emit_callback
        self.voice_enabled = voice_enabled
        self.tts_provider = tts_provider
        self.piper_base_url = piper_base_url
        self.sample_rate = sample_rate
        self.chunk_chars = chunk_chars
        self.segment_chars = segment_chars

        self.cancel_flags: Dict[str, asyncio.Event] = {}
        self.interrupted_requests: set[str] = (
            set()
        )  # Track immediately interrupted requests
        self.queues: Dict[str, asyncio.Queue[str]] = {}
        self.text_sent: Dict[str, bool] = {}
        self.metrics: Dict[str, VoiceMetrics] = {}
        self.streaming_tasks: Dict[str, asyncio.Task] = {}

        # Parallel voice: buffer + segment tracking
        self.text_buffers: Dict[str, str] = {}
        self.last_tts_offsets: Dict[str, int] = {}
        self.segment_counters: Dict[str, int] = {}
        self.voice_tasks: Dict[str, list[asyncio.Task]] = {}
        self.tts_ready: Dict[str, asyncio.Event] = {}

        self.piper_provider: Optional[PiperStreamProviderWithCancel] = None
        if tts_provider in ("piper_http", "piper_stream") and piper_base_url:
            self.piper_provider = PiperStreamProviderWithCancel(
                base_url=piper_base_url,
                sample_rate=sample_rate,
            )

    def _find_boundary(self, text: str) -> int:
        """Find segment boundary: sentence end or max chars."""
        # Look for sentence endings: . ! ? followed by space or end
        match = re.search(r"[.!?]\s+", text)
        if match:
            return match.end()
        # Fallback: split by max chars
        if len(text) >= self.segment_chars:
            return self.segment_chars
        return 0

    def _should_drop_voice(self, request_id: str) -> bool:
        """Check if we should drop voice chunks (request was cancelled)."""
        ev = self.cancel_flags.get(request_id)
        return bool(ev and ev.is_set())

    async def on_timeline_delta(self, delta: DeliveryTextDeltaV1):
        """Handle incoming text delta with parallel voice streaming."""
        request_id = delta["request_id"]
        text_delta = delta["text_delta"]
        is_final = delta.get("is_final", False)

        if request_id not in self.text_buffers:
            self.text_buffers[request_id] = ""
            self.last_tts_offsets[request_id] = 0
            self.segment_counters[request_id] = 0
            self.voice_tasks[request_id] = []
            self.cancel_flags[request_id] = asyncio.Event()
            self.metrics[request_id] = VoiceMetrics(request_id)
            self.metrics[request_id].request_start_ts = time.time()
            self.tts_ready[request_id] = asyncio.Event()

        # Append to buffer
        self.text_buffers[request_id] += text_delta
        current_text = self.text_buffers[request_id]

        # Emit text delta immediately
        self.emit_callback(
            {
                "request_id": request_id,
                "type": "render.text.delta",
                "sequence": delta.get("sequence", 0),
                "payload": {"text": current_text},
                "ts": time.time(),
            }
        )

        # Check for segment boundaries and launch TTS in parallel
        while True:
            boundary = self._find_boundary(
                current_text[self.last_tts_offsets[request_id] :]
            )
            if boundary == 0:
                break

            boundary_pos = self.last_tts_offsets[request_id] + boundary
            segment_text = current_text[
                self.last_tts_offsets[request_id] : boundary_pos
            ]

            if segment_text.strip():
                self.segment_counters[request_id] += 1
                segment_id = f"{request_id}:s{self.segment_counters[request_id]}"

                # Launch TTS immediately for this segment
                task = asyncio.create_task(
                    self._generate_segment_voice(request_id, segment_id, segment_text)
                )
                self.voice_tasks[request_id].append(task)

            self.last_tts_offsets[request_id] = boundary_pos

        # Handle final text - synthesize any remaining
        if is_final and self.last_tts_offsets[request_id] < len(current_text):
            remaining = current_text[self.last_tts_offsets[request_id] :]
            if remaining.strip():
                self.segment_counters[request_id] += 1
                segment_id = f"{request_id}:s{self.segment_counters[request_id]}"
                task = asyncio.create_task(
                    self._generate_segment_voice(request_id, segment_id, remaining)
                )
                self.voice_tasks[request_id].append(task)

    async def _generate_segment_voice(
        self, request_id: str, segment_id: str, text: str
    ):
        """Generate voice for a single segment immediately."""
        if not self.voice_enabled or not self.piper_provider:
            return

        if request_id in self.metrics:
            if self.metrics[request_id].tts_start_ts is None:
                self.metrics[request_id].tts_start_ts = time.time()
            self.metrics[request_id].backend = "piper_stream"

        seg_bytes = 0
        seg_ttfc_ns = 0
        seg_start = time.time()
        seg_first_chunk = None
        was_cancelled = False
        seg_idx = self.segment_counters.get(request_id, 0)

        voice_cache = get_voice_cache()
        asyncio.create_task(
            voice_cache.start_segment(
                request_id=request_id,
                segment_id=segment_id,
                sample_rate=self.sample_rate,
                channels=1,
                encoding="pcm_s16le",
            )
        )
        first_chunk_global = None
        if request_id in self.metrics:
            first_chunk_global = self.metrics[request_id].tts_first_chunk_ts

        try:
            seq = 0
            async for chunk in self.piper_provider.synthesize_stream(
                text=text,
                request_id=segment_id,
                cancel_event=self.cancel_flags.get(request_id),
            ):
                # First check - stop getting more chunks
                if self._should_drop_voice(request_id):
                    was_cancelled = True
                    break

                if seg_first_chunk is None:
                    seg_first_chunk = time.time()
                    seg_ttfc_ns = int((seg_first_chunk - seg_start) * 1_000_000_000)

                if self.metrics.get(request_id):
                    if self.metrics[request_id].tts_first_chunk_ts is None:
                        self.metrics[request_id].tts_first_chunk_ts = seg_first_chunk
                    audio_b64 = chunk.get("payload", {}).get("audio_b64", "")
                    if audio_b64:
                        self.metrics[request_id].bytes_streamed += len(audio_b64)
                        self.metrics[request_id].chunks_count += 1
                        seg_bytes += len(audio_b64)

                # Second check - anti-race, drop if cancelled just before emit
                if self._should_drop_voice(request_id):
                    was_cancelled = True
                    break

                self.emit_callback(
                    {
                        "request_id": request_id,
                        "type": "render.voice.delta",
                        "sequence": chunk.get("sequence", seq),
                        "payload": {
                            "encoding": "pcm_s16le",
                            "sample_rate": self.sample_rate,
                            "channels": 1,
                            **chunk.get("payload", {}),
                            "segment_id": segment_id,
                        },
                        "ts": time.time(),
                    }
                )

                audio_b64 = chunk.get("payload", {}).get("audio_b64", "")
                if audio_b64:
                    try:
                        pcm = base64.b64decode(audio_b64)
                        asyncio.create_task(
                            voice_cache.append_audio(request_id, segment_id, pcm)
                        )
                    except Exception:
                        pass

                seq += 1

            if self.metrics.get(request_id):
                self.metrics[request_id].tts_end_ts = time.time()

        except asyncio.CancelledError:
            was_cancelled = True
            if self.metrics.get(request_id):
                self.metrics[request_id].cancelled = True
                self.metrics[request_id].cancel_ts = time.time()
        except Exception as e:
            print(f"Voice segment error: {e}")

        # Mark segment complete in cache
        asyncio.create_task(voice_cache.complete_segment(request_id, segment_id))

        # Project TTS step to graph (fail-open)
        try:
            from denis_unified_v1.delivery.graph_projection import get_voice_projection

            get_voice_projection().project_tts_step(
                request_id=request_id,
                segment_id=segment_id,
                text=text,
                segment_idx=seg_idx,
                ttfc_ns=seg_ttfc_ns,
                bytes_sent=seg_bytes,
                cancelled=was_cancelled,
            )
        except Exception:
            pass

    async def on_interrupt(self, interrupt: DeliveryInterruptV1):
        """Handle interrupt/cancel - cancels all voice tasks + server-side cancel."""
        request_id = interrupt["request_id"]

        # Set cancelled flag to stop local streaming
        if request_id not in self.cancel_flags:
            self.cancel_flags[request_id] = asyncio.Event()
        self.cancel_flags[request_id].set()

        # IMMEDIATELY mark as interrupted to stop any pending emissions
        self.interrupted_requests.add(request_id)

        # Mark as cancelled in metrics
        if request_id in self.metrics:
            self.metrics[request_id].cancelled = True
            self.metrics[request_id].cancel_ts = time.time()

        # Cancel all voice tasks for this request
        if request_id in self.voice_tasks:
            for task in self.voice_tasks[request_id]:
                if not task.done():
                    task.cancel()

        # Cancel server-side streams on nodo2 for each segment
        if self.piper_provider and hasattr(self.piper_provider, "cancel_request"):
            try:
                max_seg = self.segment_counters.get(request_id, 0)
                segments_to_cancel = set()
                for i in range(1, max(1, max_seg) + 1):
                    segments_to_cancel.add(f"{request_id}:s{i}")
                segments_to_cancel.add(request_id)

                for seg_id in segments_to_cancel:
                    await self.piper_provider.cancel_request(seg_id)
                print(
                    f"DEBUG: Cancelled {len(segments_to_cancel)} segments for {request_id}"
                )
            except Exception as e:
                print(f"Server-side cancel error: {e}")

        # Clear queues
        if request_id in self.queues:
            while not self.queues[request_id].empty():
                try:
                    self.queues[request_id].get_nowait()
                except asyncio.QueueEmpty:
                    break

        # Clear voice tasks
        self.voice_tasks[request_id] = []

        # Always emit cancelled event - THIS IS KEY
        self.emit_callback(
            {
                "request_id": request_id,
                "type": "render.voice.cancelled",
                "payload": {"reason_code": interrupt.get("reason", "user_interrupt")},
                "ts": time.time(),
            }
        )

    def get_metrics(self, request_id: str) -> dict:
        """Get voice metrics for a request."""
        if request_id in self.metrics:
            return self.metrics[request_id].to_dict()
        return {}

    async def _process_request(self, request_id: str):
        """Process text queue and generate voice."""
        while True:
            if self.cancel_flags[request_id].is_set():
                break

            try:
                text = await asyncio.wait_for(
                    self.queues[request_id].get(), timeout=0.5
                )
            except asyncio.TimeoutError:
                continue

            if not text:
                continue

            self.emit_callback(
                RenderTextDeltaV1(request_id=request_id, text_delta=text, sequence=0)
            )
            self.text_sent[request_id] = True

            if self.voice_enabled and self.piper_provider:
                await self._generate_voice_streaming(request_id, text)

    async def _generate_voice_streaming(self, request_id: str, text: str):
        """Generate voice using streaming TTS."""
        if request_id not in self.metrics:
            self.metrics[request_id] = VoiceMetrics(request_id)
            self.metrics[request_id].request_start_ts = time.time()

        metrics = self.metrics[request_id]
        metrics.tts_start_ts = time.time()
        metrics.backend = (
            "piper_stream" if self.tts_provider == "piper_stream" else "piper_http"
        )

        try:
            if self.piper_provider:
                async for chunk in self.piper_provider.synthesize_stream(
                    text=text,
                    request_id=request_id,
                    cancel_event=self.cancel_flags[request_id],
                ):
                    # First check
                    if self._should_drop_voice(request_id):
                        break

                    if metrics.tts_first_chunk_ts is None:
                        metrics.tts_first_chunk_ts = time.time()

                    audio_b64 = chunk.get("payload", {}).get("audio_b64", "")
                    if audio_b64:
                        metrics.bytes_streamed += len(audio_b64)
                        metrics.chunks_count += 1

                    # Second check - anti-race
                    if self._should_drop_voice(request_id):
                        break

                    self.emit_callback(
                        {
                            "request_id": request_id,
                            "type": "render.voice.delta",
                            "sequence": chunk.get("sequence", 0),
                            "payload": {
                                "encoding": "pcm_s16le",
                                "sample_rate": self.sample_rate,
                                "channels": 1,
                                **chunk.get("payload", {}),
                            },
                            "ts": time.time(),
                        }
                    )

                metrics.tts_end_ts = time.time()

        except asyncio.CancelledError:
            metrics.cancelled = True
            metrics.cancel_ts = time.time()
        except Exception as e:
            print(f"Voice generation error: {e}")

    async def _filler_task(self, request_id: str):
        """Emit filler if no text received within timeout."""
        await asyncio.sleep(0.7)

        if (
            not self.cancel_flags[request_id].is_set()
            and not self.text_sent[request_id]
        ):
            filler_text = "Déjame pensar..."

            self.emit_callback(
                RenderTextDeltaV1(
                    request_id=request_id, text_delta=filler_text, sequence=-1
                )
            )

            if self.voice_enabled and self.piper_provider:
                await self._generate_voice_streaming(request_id, filler_text)

    def _chunk_text(self, text: str) -> list[str]:
        return [
            text[i : i + self.chunk_chars]
            for i in range(0, len(text), self.chunk_chars)
        ]
