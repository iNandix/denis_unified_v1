"""
Denis Kernel - Normalizer Node
===============================
Cleans and normalizes input before NLU/Loops see it.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import logging

from denis_unified_v1.kernel.bus.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


@dataclass
class NormalizerConfig:
    """Configuration for Normalizer."""

    detect_language: bool = True
    min_text_length: int = 1
    strip_extra_spaces: bool = True
    lowercase: bool = False


class Normalizer:
    """
    Normalizes input before NLU processes it.

    Responsibilities:
    - Basic cleanup (spaces, encoding)
    - Language detection (simple)
    - Turn-taking detection (end of turn vs streaming)
    - Segment into sentences if needed

    Consumes: input.chunk.text
    Emits: input.chunk.normalized
    """

    def __init__(
        self,
        event_bus=None,
        config: Optional[NormalizerConfig] = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.config = config or NormalizerConfig()

        self._subscribe()
        logger.info("Normalizer initialized")

    def _subscribe(self):
        """Subscribe to input events."""
        self.event_bus.subscribe("input.chunk.text", self._on_chunk)

    async def _on_chunk(self, event: Event):
        """Handle incoming text chunks."""
        text = event.payload.get("text", "")

        if not text or len(text) < self.config.min_text_length:
            return

        normalized = self._normalize(text)

        is_end_of_turn = self._detect_end_of_turn(event)

        output_event = Event(
            trace_id=event.trace_id,
            session_id=event.session_id,
            turn_id=event.turn_id,
            seq=event.seq,
            source="normalizer",
            type="input.chunk.normalized",
            priority=event.priority,
            commit_level=event.commit_level,
            payload={
                "original_text": text,
                "text": normalized,
                "is_final": event.payload.get("is_final", True),
                "is_end_of_turn": is_end_of_turn,
                "char_count": len(normalized),
                "word_count": len(normalized.split()),
            },
        )

        await self.event_bus.emit(output_event)

    def _normalize(self, text: str) -> str:
        """Normalize text."""
        result = text

        if self.config.strip_extra_spaces:
            result = re.sub(r"\s+", " ", result)
            result = result.strip()

        if self.config.lowercase:
            result = result.lower()

        return result

    def _detect_end_of_turn(self, event: Event) -> bool:
        """Detect if this is the end of a turn."""
        if event.payload.get("is_final", True):
            return True

        text = event.payload.get("text", "")

        end_markers = [".", "?", "!", "...", "—"]
        for marker in end_markers:
            if text.rstrip().endswith(marker):
                return True

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get normalizer stats."""
        return {
            "config": {
                "detect_language": self.config.detect_language,
                "min_text_length": self.config.min_text_length,
            },
        }
