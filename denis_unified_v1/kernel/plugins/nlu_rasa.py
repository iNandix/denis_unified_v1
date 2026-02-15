"""
Denis Kernel - NLU Stream Plugin (Rasa)
=========================================
Real Rasa NLU integration with incremental hypotheses.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

import httpx

from denis_unified_v1.kernel.bus.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


RASA_URL = "http://localhost:5005"


@dataclass
class RasaConfig:
    """Configuration for Rasa NLU."""

    rasa_url: str = RASA_URL
    timeout_ms: int = 5000
    emit_partial: bool = True


class RasaNLUPlugin:
    """
     Rasa NLU plugin for Denis Kernel.

     Consumes: input.chunk.normalized
     Emits: nlu.intent.hypothesis, nlu.entities.hypothesis, nlu.slots.patch

    特点:
     - Non-blocking (async)
     - Emits hypotheses as they arrive
     - No routing decision (only proposes)
    """

    def __init__(
        self,
        event_bus=None,
        config: Optional[RasaConfig] = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.config = config or RasaConfig()
        self._http_client = httpx.AsyncClient(timeout=self.config.timeout_ms / 1000)
        self._running = False
        self._tasks: Dict[str, asyncio.Task] = {}

        self._subscribe_to_events()
        logger.info(f"RasaNLUPlugin initialized: {self.config.rasa_url}")

    def _subscribe_to_events(self):
        """Subscribe to input events."""
        self.event_bus.subscribe("input.chunk.normalized", self._on_input_chunk)
        self.event_bus.subscribe("input.chunk.text", self._on_input_chunk)

    async def _on_input_chunk(self, event: Event):
        """Handle incoming text chunks."""
        if not event.payload.get("is_final", True):
            return

        text = event.payload.get("text", "")
        if not text:
            return

        trace_id = event.trace_id
        session_id = event.session_id

        task = asyncio.create_task(self._process_text(text, trace_id, session_id))
        self._tasks[trace_id] = task

    async def _process_text(self, text: str, trace_id: str, session_id: str):
        """Process text through Rasa NLU."""
        try:
            response = await self._http_client.post(
                f"{self.config.rasa_url}/model/parse",
                json={"text": text},
            )

            if response.status_code != 200:
                logger.warning(f"Rasa returned {response.status_code}")
                await self._emit_error(
                    trace_id, session_id, f"Rasa error: {response.status_code}"
                )
                return

            nlu_data = response.json()

            await self._emit_intent_hypothesis(nlu_data, trace_id, session_id)
            await self._emit_entities_hypothesis(nlu_data, trace_id, session_id)
            await self._emit_slots_patch(nlu_data, trace_id, session_id)

            logger.debug(
                f"Rasa processed: {trace_id} -> intent={nlu_data.get('intent', {}).get('name')}"
            )

        except httpx.TimeoutException:
            logger.warning(f"Rasa timeout for {trace_id}")
            await self._emit_error(trace_id, session_id, "timeout")
        except Exception as e:
            logger.error(f"Rasa error: {e}")
            await self._emit_error(trace_id, session_id, str(e))
        finally:
            self._tasks.pop(trace_id, None)

    async def _emit_intent_hypothesis(
        self, nlu_data: Dict, trace_id: str, session_id: str
    ):
        """Emit nlu.intent.hypothesis event."""
        intent_data = nlu_data.get("intent", {})

        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="rasa_nlu",
            type="nlu.intent.hypothesis",
            priority=0,
            payload={
                "intent": intent_data.get("name", "unknown"),
                "confidence": intent_data.get("confidence", 0.0),
                "text": nlu_data.get("text", ""),
            },
        )
        await self.event_bus.emit(event)

    async def _emit_entities_hypothesis(
        self, nlu_data: Dict, trace_id: str, session_id: str
    ):
        """Emit nlu.entities.hypothesis event."""
        entities = []
        for entity in nlu_data.get("entities", []):
            entities.append(
                {
                    "name": entity.get("entity"),
                    "value": entity.get("value"),
                    "confidence": entity.get("confidence", 1.0),
                    "start": entity.get("start"),
                    "end": entity.get("end"),
                }
            )

        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="rasa_nlu",
            type="nlu.entities.hypothesis",
            priority=1,
            payload={
                "entities": entities,
                "text": nlu_data.get("text", ""),
            },
        )
        await self.event_bus.emit(event)

    async def _emit_slots_patch(self, nlu_data: Dict, trace_id: str, session_id: str):
        """Emit nlu.slots.patch event with extracted slots."""
        slots = {}

        for entity in nlu_data.get("entities", []):
            entity_name = entity.get("entity")
            entity_value = entity.get("value")
            if entity_name:
                slots[entity_name] = entity_value

        if not slots:
            return

        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="rasa_nlu",
            type="nlu.slots.patch",
            priority=2,
            payload={
                "slots": slots,
            },
        )
        await self.event_bus.emit(event)

    async def _emit_error(self, trace_id: str, session_id: str, error: str):
        """Emit error event."""
        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="rasa_nlu",
            type="nlu.error",
            priority=-1,
            payload={
                "error": error,
            },
        )
        await self.event_bus.emit(event)

    async def health_check(self) -> Dict[str, Any]:
        """Check Rasa health."""
        try:
            response = await self._http_client.post(
                f"{self.config.rasa_url}/model/parse",
                json={"text": "test"},
            )
            if response.status_code == 200:
                return {"status": "healthy", "rasa_version": "3.6.0"}
            return {"status": "unhealthy", "rasa_status": response.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def parse(self, text: str) -> Dict[str, Any]:
        """Direct parse method for testing."""
        try:
            response = await self._http_client.post(
                f"{self.config.rasa_url}/model/parse",
                json={"text": text},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Get plugin stats."""
        return {
            "active_tasks": len(self._tasks),
            "config": {
                "rasa_url": self.config.rasa_url,
                "timeout_ms": self.config.timeout_ms,
            },
        }


# Global instance
_rasa_plugin: Optional[RasaNLUPlugin] = None


def get_rasa_plugin() -> RasaNLUPlugin:
    """Get or create the Rasa NLU plugin."""
    global _rasa_plugin
    if _rasa_plugin is None:
        _rasa_plugin = RasaNLUPlugin()
    return _rasa_plugin


async def initialize_rasa_plugin() -> RasaNLUPlugin:
    """Initialize the Rasa NLU plugin."""
    plugin = get_rasa_plugin()
    health = await plugin.health_check()
    logger.info(f"Rasa plugin health: {health}")
    return plugin
