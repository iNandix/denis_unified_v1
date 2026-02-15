"""
Denis Kernel - Delivery Composer + Renderer
============================================
Handles pacing, fillers, and output delivery.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import logging

from denis_unified_v1.kernel.bus.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


class DeliveryComposer:
    """
    Composes delivery timeline with pacing, cues, and formatting.

    Consumes: llm.token.delta, tool.result
    Emits: delivery.timeline.delta, delivery.cue.*
    """

    def __init__(
        self,
        event_bus=None,
        enable_cues: bool = True,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.enable_cues = enable_cues

        self._subscribe()
        logger.info("DeliveryComposer initialized")

    def _subscribe(self):
        """Subscribe to LLM and tool events."""
        self.event_bus.subscribe("llm.token.delta", self._on_token)
        self.event_bus.subscribe("tool.result", self._on_tool_result)

    async def _on_token(self, event: Event):
        """Handle incoming token."""
        text = event.payload.get("text", "")
        is_thinking = event.payload.get("is_thinking", False)

        segment = Event(
            trace_id=event.trace_id,
            session_id=event.session_id,
            source="delivery_composer",
            type="delivery.timeline.delta",
            priority=2,
            payload={
                "segment_id": f"seg-{uuid.uuid4().hex[:6]}",
                "text": text,
                "is_thinking": is_thinking,
                "timestamp": event.ts,
            },
        )

        await self.event_bus.emit(segment)

    async def _on_tool_result(self, event: Event):
        """Handle tool result."""
        tool_name = event.payload.get("tool_name", "unknown")
        status = event.payload.get("status", "unknown")
        output = event.payload.get("output", {})

        segment = Event(
            trace_id=event.trace_id,
            session_id=event.session_id,
            source="delivery_composer",
            type="delivery.timeline.delta",
            priority=1,
            payload={
                "segment_id": f"tool-{uuid.uuid4().hex[:6]}",
                "text": f"[{tool_name}: {status}]",
                "is_tool_result": True,
            },
        )

        await self.event_bus.emit(segment)

    def get_stats(self) -> Dict[str, Any]:
        """Get composer stats."""
        return {"enabled": self.enable_cues}


class ConsoleRenderer:
    """
    Simple console renderer for text output.

    Consumes: delivery.timeline.delta
    Emits: render.text.delta
    """

    def __init__(
        self,
        event_bus=None,
        print_to_console: bool = True,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.print_to_console = print_to_console

        self._subscribe()
        logger.info("ConsoleRenderer initialized")

    def _subscribe(self):
        """Subscribe to delivery events."""
        self.event_bus.subscribe("delivery.timeline.delta", self._on_timeline)

    async def _on_timeline(self, event: Event):
        """Handle timeline delta."""
        text = event.payload.get("text", "")
        is_thinking = event.payload.get("is_thinking", False)

        if self.print_to_console:
            if is_thinking:
                print(f"🤔 {text}", end="", flush=True)
            else:
                print(f"{text}", end="", flush=True)

        render_event = Event(
            trace_id=event.trace_id,
            session_id=event.session_id,
            source="console_renderer",
            type="render.text.delta",
            priority=3,
            payload={
                "text": text,
                "is_thinking": is_thinking,
                "timestamp": event.ts,
            },
        )

        await self.event_bus.emit(render_event)

    def get_stats(self) -> Dict[str, Any]:
        """Get renderer stats."""
        return {"console_output": self.print_to_console}


# Global instances
_delivery_composer: Optional[DeliveryComposer] = None
_console_renderer: Optional[ConsoleRenderer] = None


def get_delivery_composer() -> DeliveryComposer:
    """Get or create Delivery Composer."""
    global _delivery_composer
    if _delivery_composer is None:
        _delivery_composer = DeliveryComposer()
    return _delivery_composer


def get_console_renderer() -> ConsoleRenderer:
    """Get or create Console Renderer."""
    global _console_renderer
    if _console_renderer is None:
        _console_renderer = ConsoleRenderer()
    return _console_renderer
