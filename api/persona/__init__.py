"""Persona frontdoor modules (WS15).

Persona is the only allowed event emitter to the WS event bus.
Other modules must call `api.persona.event_router.persona_emit(...)`.
"""

__all__ = [
    "persona_emit",
]

from .event_router import persona_emit  # noqa: E402

