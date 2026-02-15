"""
Denis Kernel - LLM Worker Node
==============================
Streaming LLM worker that generates responses.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import logging

from denis_unified_v1.kernel.bus.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


RESPONSE_TEMPLATES = {
    "fast_talk": {
        "greet": ["Hola!", "¡Hola! ¿Qué tal?", "¡Buenos días!", "¡Hey!"],
        "thanks": ["¡De nada!", "¡Para eso estoy!", "¡Ahora sí!"],
        "bye": ["¡Hasta luego!", "¡Nos vemos!", "¡Chao!"],
    },
    "standard": {
        "default": [
            "Entendido. {response}",
            "Perfecto. {response}",
            "De acuerdo. {response}",
            "Ya veo. {response}",
        ],
    },
    "tool": {
        "deployment_exec": "Ejecutando despliegue...",
        "file_delete": "Eliminando archivo...",
        "file_modify": "Modificando archivo...",
        "backup_db": "Iniciando backup...",
        "calendar": "Consultando calendario...",
        "search": "Buscando información...",
        "memory": "Consultando memoria...",
        "hass_control": "Controlando Home Assistant...",
    },
}


class LLMWorker:
    """
    LLM Worker node for streaming response generation.

    Consumes: policy.route.commit
    Emits: llm.token.delta, llm.final

    MVP: Template-based responses (can be swapped to real LLM)
    """

    def __init__(
        self,
        event_bus=None,
        template_responses: Optional[Dict] = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.template_responses = template_responses or RESPONSE_TEMPLATES
        self._running = False
        self._active_tasks: Dict[str, asyncio.Task] = {}

        self._subscribe()
        logger.info("LLMWorker initialized")

    def _subscribe(self):
        """Subscribe to route commit events."""
        self.event_bus.subscribe("policy.route.commit", self._on_route_commit)

    async def _on_route_commit(self, event: Event):
        """Handle route commit and generate response."""
        route_id = event.payload.get("route_id", "standard")
        reasoning_mode = event.payload.get("reasoning_mode", "direct")
        trace_id = event.trace_id
        session_id = event.session_id

        task = asyncio.create_task(
            self._generate_response(route_id, reasoning_mode, trace_id, session_id)
        )
        self._active_tasks[trace_id] = task

    async def _generate_response(
        self,
        route_id: str,
        reasoning_mode: str,
        trace_id: str,
        session_id: str,
    ):
        """Generate response based on route."""

        response_text = self._get_template_response(route_id, reasoning_mode)

        if reasoning_mode in ["deliberate", "verify"]:
            thinking_cue = self._get_thinking_cue()
            await self._emit_token(thinking_cue, trace_id, session_id, is_thinking=True)
            await asyncio.sleep(0.3)

        words = response_text.split()
        for i, word in enumerate(words):
            is_final = i == len(words) - 1
            await self._emit_token(word + " ", trace_id, session_id, is_final)
            await asyncio.sleep(0.05)

        await self._emit_final(response_text, trace_id, session_id)

        self._active_tasks.pop(trace_id, None)

    def _get_template_response(self, route_id: str, reasoning_mode: str) -> str:
        """Get template response based on route."""

        if route_id == "fast_talk":
            responses = self.template_responses.get("fast_talk", {}).get("greet", [])
            return responses[0] if responses else "¡Hola!"

        if route_id == "tool":
            tool_responses = self.template_responses.get("tool", {})
            return tool_responses.get("default", "Entendido. Procesando...")

        responses = self.template_responses.get("standard", {}).get("default", [])
        return responses[0].format(response="") if responses else "Entendido."

    def _get_thinking_cue(self) -> str:
        """Get a thinking cue for deliberate mode."""
        cues = [
            "Déjame pensar...",
            "Un momento...",
            "Procesando...",
            "Analizando...",
        ]
        return cues[hash(str(uuid.uuid4())) % len(cues)]

    async def _emit_token(
        self,
        text: str,
        trace_id: str,
        session_id: str,
        is_final: bool = False,
        is_thinking: bool = False,
    ):
        """Emit token delta event."""
        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="llm_worker",
            type="llm.token.delta",
            priority=1,
            payload={
                "text": text,
                "is_final": is_final,
                "is_thinking": is_thinking,
            },
        )
        await self.event_bus.emit(event)

    async def _emit_final(
        self,
        text: str,
        trace_id: str,
        session_id: str,
    ):
        """Emit final response event."""
        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="llm_worker",
            type="llm.final",
            priority=0,
            payload={
                "text": text,
                "tokens_used": len(text.split()),
                "model": "template",
            },
        )
        await self.event_bus.emit(event)

    def get_stats(self) -> Dict[str, Any]:
        """Get worker stats."""
        return {
            "active_tasks": len(self._active_tasks),
        }


# Global instance
_llm_worker: Optional[LLMWorker] = None


def get_llm_worker() -> LLMWorker:
    """Get or create LLM Worker."""
    global _llm_worker
    if _llm_worker is None:
        _llm_worker = LLMWorker()
    return _llm_worker
