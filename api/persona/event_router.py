"""Persona event router (WS15).

Only Persona may emit events to the WS event bus. All other modules must call
`persona_emit(...)` (not `api.event_bus.emit_event`).
"""

from __future__ import annotations

from collections import Counter
import threading
from typing import Any

from api.event_bus import emit_event, persona_emitter_context


def _infer_channel(event_type: str) -> str:
    t = (event_type or "").strip()
    if t.startswith("compiler.") or t.startswith("retrieval."):
        return "compiler"
    if t.startswith("voice."):
        return "voice"
    if t.startswith("control_room."):
        return "control_room"
    if t.startswith("rag."):
        return "rag"
    if t.startswith("tool."):
        return "tool"
    if t.startswith("scrape.") or t.startswith("scraping."):
        return "scrape"
    if t == "chat.message" or t.startswith("plan."):
        return "text"
    if t.startswith("agent."):
        return "ops"
    if t.startswith("ops.") or t in {"error", "graph.mutation", "indexing.upsert", "run.step"}:
        return "ops"
    return "ops"


_stats_lock = threading.Lock()
_stats_total = 0
_stats_stored_true = 0
_stats_stored_false = 0
_stats_by_channel: Counter[str] = Counter()
_stats_by_type: Counter[str] = Counter()
_last_emit_ts = ""


def get_persona_emitter_stats() -> dict[str, Any]:
    with _stats_lock:
        return {
            "emitter": "denis_persona",
            "total": int(_stats_total),
            "stored_true": int(_stats_stored_true),
            "stored_false": int(_stats_stored_false),
            "by_channel": dict(_stats_by_channel),
            "by_type_top": dict(_stats_by_type.most_common(25)),
            "last_emit_ts": str(_last_emit_ts or ""),
        }


def persona_emit(
    *,
    conversation_id: str,
    trace_id: str | None,
    type: str,
    severity: str = "info",
    ui_hint: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    channel: str | None = None,
    stored: bool = True,
) -> dict[str, Any]:
    """Emit an event as denis_persona (fail-open at the event bus layer)."""
    ch = (channel or "").strip() or _infer_channel(type)
    stored_flag = bool(stored)
    global _stats_total, _stats_stored_true, _stats_stored_false, _last_emit_ts
    try:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
    except Exception:
        ts = ""
    with _stats_lock:
        _stats_total += 1
        if stored_flag:
            _stats_stored_true += 1
        else:
            _stats_stored_false += 1
        _stats_by_channel[ch] += 1
        _stats_by_type[str(type or "")] += 1
        if ts:
            _last_emit_ts = ts

    with persona_emitter_context():
        return emit_event(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type=type,
            severity=severity,
            ui_hint=ui_hint,
            payload=payload,
            emitter="denis_persona",
            channel=ch,
            stored=stored_flag,
        )
