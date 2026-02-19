"""Event->Graph mutation mappings (v1).

This module keeps an explicit table of supported `event_v1` types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class MappingResult:
    handled: bool
    component_id: str | None = None
    mutation_kinds: list[str] | None = None


MaterializeFn = Callable[[dict[str, Any]], MappingResult]


SUPPORTED_EVENT_TYPES_V1: set[str] = {
    "agent.decision_trace_summary",
    "agent.reasoning.summary",
    "chat.message",
    "compiler.start",
    "compiler.result",
    "compiler.error",
    "compiler.fallback_start",
    "compiler.fallback_result",
    "retrieval.start",
    "retrieval.result",
    "voice.session.started",
    "voice.asr.partial",
    "voice.asr.final",
    "voice.tts.requested",
    "voice.tts.audio.ready",
    "voice.tts.done",
    "voice.error",
    "control_room.action.updated",
    "control_room.approval.requested",
    "control_room.approval.resolved",
    "control_room.run.spawned",
    "control_room.task.created",
    "control_room.task.updated",
    "error",
    "indexing.upsert",
    "ops.metric",
    "rag.context.compiled",
    "rag.search.result",
    "rag.search.start",
    "run.step",
    "scraping.done",
    "scraping.page",
    # WS23-G Neuroplasticity
    "neuro.wake.start",
    "neuro.layer.snapshot",
    "neuro.consciousness.snapshot",
    "neuro.turn.update",
    "neuro.consciousness.update",
    "persona.state.update",
}
