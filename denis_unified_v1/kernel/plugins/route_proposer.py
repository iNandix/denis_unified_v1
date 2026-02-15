"""
Denis Kernel - Route Proposer Plugin
====================================
Converts cognitive_router.py to a plugin that proposes routes.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import logging

from denis_unified_v1.kernel.bus.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


TOOL_KEYWORDS = {
    "deployment_exec": ["deploy", "despliegue", "deployment", "release"],
    "file_delete": ["borra", "elimina", "delete", "borrar"],
    "file_modify": ["modifica", "edita", "cambia", "modify", "edit"],
    "backup_db": ["backup", "respaldo", "backup de base de datos"],
    "calendar": ["calendario", "cita", "meeting", "reunión"],
    "search": ["busca", "buscar", "search", "encuentra"],
    "memory": ["recuerda", "memoria", "what do you remember"],
}


class RouteProposer:
    """
    Route proposer plugin - converts cognitive patterns to proposals.

    Consumes:
    - nlu.intent.hypothesis
    - nlu.entities.hypothesis
    - nlu.slots.patch
    - dialogue.signal

    Emits:
    - policy.route.proposed {route_id, tool_required, confidence, pattern_id}

    Key: Proposes only. Governor decides.
    """

    def __init__(self, event_bus=None):
        self.event_bus = event_bus or get_event_bus()

        self._subscribe()
        logger.info("RouteProposer initialized")

    def _subscribe(self):
        """Subscribe to NLU events."""
        self.event_bus.subscribe("nlu.intent.hypothesis", self._on_intent)
        self.event_bus.subscribe("nlu.entities.hypothesis", self._on_entities)
        self.event_bus.subscribe("dialogue.signal", self._on_dialogue)

    async def _on_intent(self, event: Event):
        """Handle intent hypothesis."""
        intent = event.payload.get("intent", "unknown")
        confidence = event.payload.get("confidence", 0.5)
        text = event.payload.get("text", "")

        tool_name = self._detect_tool_need(intent, text)
        tool_required = tool_name is not None

        route_id = self._decide_route(intent, confidence, tool_required)

        proposal = Event(
            trace_id=event.trace_id,
            session_id=event.session_id,
            source="route_proposer",
            type="policy.route.proposed",
            priority=0,
            payload={
                "route_id": route_id,
                "tool_required": tool_required,
                "tool_name": tool_name,
                "confidence": confidence,
                "intent": intent,
                "pattern_id": f"intent_{intent}",
                "text_sample": text[:50],
            },
        )

        await self.event_bus.emit(proposal)
        logger.debug(
            f"Route proposed: {route_id} (intent={intent}, confidence={confidence}, tool={tool_name})"
        )

    async def _on_entities(self, event: Event):
        """Handle entities (informational, no proposal)."""
        pass

    async def _on_dialogue(self, event: Event):
        """Handle dialogue signals from ParlAI."""
        act = event.payload.get("act", "")

        if act in ["confirm_action", "ask"]:
            proposal = Event(
                trace_id=event.trace_id,
                session_id=event.session_id,
                source="route_proposer",
                type="policy.route.proposed",
                priority=0,
                payload={
                    "route_id": "standard",
                    "tool_required": False,
                    "confidence": 0.8,
                    "pattern_id": f"dialogue_{act}",
                    "dialogue_act": act,
                },
            )
            await self.event_bus.emit(proposal)

    def _detect_tool_need(self, intent: str, text: str) -> Optional[str]:
        """Detect if a tool is needed based on intent or keywords. Returns tool name or None."""
        text_lower = text.lower()

        for tool, keywords in TOOL_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return tool

        intent_lower = intent.lower() if intent else ""
        tool_intents = ["tool", "execute", "action", "run", "start", "stop"]
        if any(ti in intent_lower for ti in tool_intents):
            return "generic_tool"

        return None

    def _decide_route(
        self,
        intent: str,
        confidence: float,
        tool_required: bool,
    ) -> str:
        """Decide proposed route."""
        fast_intents = ["greet", "thanks", "bye", "hello", "goodbye", "affirm", "deny"]
        project_intents = [
            "project",
            "plan",
            "build",
            "create",
            "implement",
            "deploy_project",
        ]
        complex_intents = ["analyze", "research", "compare", "evaluate", "design"]

        intent_lower = intent.lower() if intent else ""

        if intent_lower in fast_intents and confidence >= 0.7:
            return "fast_talk"

        if tool_required:
            # Check if it's a complex task requiring project/toolchain
            if any(ci in intent_lower for ci in complex_intents):
                return "project"
            if any(pi in intent_lower for pi in project_intents):
                return "project"
            return "tool"

        if confidence >= 0.8:
            return "standard"

        if confidence < 0.5:
            return "deliberate"

        return "standard"

    def get_stats(self) -> Dict[str, Any]:
        """Get proposer stats."""
        return {}


# Global instance
_route_proposer: Optional[RouteProposer] = None


def get_route_proposer() -> RouteProposer:
    """Get or create the Route Proposer."""
    global _route_proposer
    if _route_proposer is None:
        _route_proposer = RouteProposer()
    return _route_proposer
