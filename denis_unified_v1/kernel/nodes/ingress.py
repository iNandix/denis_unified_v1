"""
Denis Kernel - Ingress Node
=============================
Entry point for all inputs (text, voice, API, events).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import logging

from denis_unified_v1.kernel.bus.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


@dataclass
class ChunkConfig:
    """Configuration for chunking."""

    max_chars: int = 500
    min_chars: int = 10
    chunk_overlap: int = 20


class Ingress:
    """
    Single entry point for all inputs.

    Responsibilities:
    - Receive input from any source (text, voice, API)
    - Chunk if applicable
    - Emit input.chunk.text or input.chunk.audio events

    MVP: Text input only.
    """

    def __init__(
        self,
        event_bus=None,
        chunk_config: Optional[ChunkConfig] = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.chunk_config = chunk_config or ChunkConfig()
        self._sequence = 0

        logger.info("Ingress initialized")

    async def ingest_text(
        self,
        text: str,
        session_id: str,
        user_id: str = "anonymous",
        is_final: bool = True,
    ) -> List[Event]:
        """
        Process text input and emit chunk events.

        Args:
            text: Raw input text
            session_id: Session identifier
            user_id: User identifier
            is_final: Whether this is the final chunk of input

        Returns:
            List of emitted events
        """
        self._sequence += 1
        trace_id = f"ing-{uuid.uuid4().hex[:8]}"

        if len(text) <= self.chunk_config.max_chars:
            event = self._create_chunk_event(
                text=text,
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                is_final=is_final,
                chunk_index=0,
                total_chunks=1,
            )
            await self.event_bus.emit(event)
            return [event]

        chunks = self._chunk_text(text)
        events = []

        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1) and is_final

            event = self._create_chunk_event(
                text=chunk,
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                is_final=is_last,
                chunk_index=i,
                total_chunks=len(chunks),
            )
            await self.event_bus.emit(event)
            events.append(event)

        logger.info(f"Ingress emitted {len(events)} chunks for trace {trace_id}")
        return events

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks."""
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + self.chunk_config.max_chars, text_len)

            if end < text_len:
                last_period = text.rfind(".", start, end)
                last_comma = text.rfind(",", start, end)
                split_point = max(last_period, last_comma)

                if split_point > start + self.chunk_config.min_chars:
                    end = split_point + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = max(end - self.chunk_config.chunk_overlap, start + 1)

        return chunks

    def _create_chunk_event(
        self,
        text: str,
        trace_id: str,
        session_id: str,
        user_id: str,
        is_final: bool,
        chunk_index: int,
        total_chunks: int,
    ) -> Event:
        """Create an input.chunk.text event."""
        return Event(
            trace_id=trace_id,
            session_id=session_id,
            turn_id=f"turn-{self._sequence}",
            seq=chunk_index,
            source="ingress",
            type="input.chunk.text",
            priority=0 if is_final else 1,
            commit_level="tentative" if not is_final else "final",
            payload={
                "text": text,
                "user_id": user_id,
                "is_final": is_final,
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
                "char_count": len(text),
            },
        )

    def create_interrupt_event(
        self,
        session_id: str,
        reason: str = "new_input",
        trace_id: Optional[str] = None,
    ) -> Event:
        """Create an input.interrupt event."""
        return Event(
            trace_id=trace_id or f"int-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            source="ingress",
            type="input.interrupt",
            priority=-1,
            commit_level="final",
            payload={
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


# Simple API entry point
async def handle_text_input(
    text: str,
    session_id: str,
    user_id: str = "anonymous",
) -> Dict[str, Any]:
    """
    API entry point for text input.

    Usage:
        await handle_text_input("Hola Denis", "session-123", "user-1")
    """
    ingress = Ingress()
    events = await ingress.ingest_text(text, session_id, user_id)

    return {
        "status": "accepted",
        "trace_id": events[0].trace_id if events else None,
        "chunks": len(events),
    }
