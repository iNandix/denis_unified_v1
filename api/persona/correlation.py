"""Correlation and turn context for Persona (WS15).

We use contextvars so downstream calls (RAG/tools/worker) can emit events with
consistent ids without threading parameters everywhere.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaContext:
    conversation_id: str
    correlation_id: str
    turn_id: str
    trace_id: str | None


_CONVERSATION_ID: ContextVar[str] = ContextVar("denis_persona_conversation_id", default="default")
_CORRELATION_ID: ContextVar[str] = ContextVar("denis_persona_correlation_id", default="")
_TURN_ID: ContextVar[str] = ContextVar("denis_persona_turn_id", default="")
_TRACE_ID: ContextVar[str | None] = ContextVar("denis_persona_trace_id", default=None)


def _new_id() -> str:
    return uuid.uuid4().hex


def get_persona_context() -> PersonaContext:
    conv = (_CONVERSATION_ID.get() or "").strip() or "default"
    corr = (_CORRELATION_ID.get() or "").strip()
    turn = (_TURN_ID.get() or "").strip()
    trace = _TRACE_ID.get()

    # Fail-open defaults if caller didn't set a context.
    if not corr:
        corr = (trace or "").strip() or _new_id()
    if not turn:
        turn = _new_id()

    return PersonaContext(
        conversation_id=conv,
        correlation_id=corr,
        turn_id=turn,
        trace_id=(trace or "").strip() or None,
    )


def get_persona_context_if_set() -> PersonaContext | None:
    """Return current persona context if any id was explicitly set, else None.

    Unlike `get_persona_context()`, this function does not generate new ids.
    """
    conv = (_CONVERSATION_ID.get() or "").strip() or "default"
    corr = (_CORRELATION_ID.get() or "").strip()
    turn = (_TURN_ID.get() or "").strip()
    trace = (_TRACE_ID.get() or "")
    trace = trace.strip() if isinstance(trace, str) else ""

    if not corr and not turn and not trace:
        return None

    return PersonaContext(
        conversation_id=conv,
        correlation_id=corr or trace,
        turn_id=turn,
        trace_id=trace or None,
    )


@contextmanager
def persona_request_context(
    *,
    conversation_id: str | None,
    trace_id: str | None,
    correlation_id: str | None = None,
    turn_id: str | None = None,
):
    """Establish persona context for a single inbound request/turn."""
    conv = (conversation_id or "").strip() or "default"
    trace = (trace_id or "").strip() or None
    corr = (correlation_id or "").strip() or (trace or "") or _new_id()
    turn = (turn_id or "").strip() or _new_id()

    t_conv = _CONVERSATION_ID.set(conv)
    t_corr = _CORRELATION_ID.set(corr)
    t_turn = _TURN_ID.set(turn)
    t_trace = _TRACE_ID.set(trace)
    try:
        yield PersonaContext(conversation_id=conv, correlation_id=corr, turn_id=turn, trace_id=trace)
    finally:
        _CONVERSATION_ID.reset(t_conv)
        _CORRELATION_ID.reset(t_corr)
        _TURN_ID.reset(t_turn)
        _TRACE_ID.reset(t_trace)
