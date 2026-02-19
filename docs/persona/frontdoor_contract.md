# Persona Frontdoor Contract (WS15)

Objetivo: `denis_persona` es el **unico** gateway y el **unico** emisor de eventos del bus WS (`event_v1`).

## Ingress (canales)
- Texto: `/v1/chat/completions` (legacy) o `/persona/chat` (nuevo).
- Voz: `/v1/voice/*` (legacy) y a futuro `/persona/voice`.
- Control Room: `/control_room/*` (legacy) y a futuro `/persona/control_room`.
- WS events: `/v1/ws` (event bus v1).

Legacy puede existir, pero **no debe emitir eventos directamente**: debe delegar a Persona.

## Correlation
Persona define por turn/request:
- `conversation_id`: string (header `X-Denis-Conversation-Id` o `default`)
- `trace_id`: string|null (header `X-Denis-Trace-Id`)
- `correlation_id`: string (por defecto = `trace_id` si existe)
- `turn_id`: string (por defecto = `trace_id` si existe)

## Emision de eventos (hard rule)
Regla: Nadie llama `api.event_bus.emit_event(...)` directo.

La unica API permitida es:
- `api.persona.event_router.persona_emit(...)`

Enforcement:
- `PERSONA_FRONTDOOR_ENFORCE=1` (default)
- Si un modulo llama `api.event_bus.emit_event` sin contexto Persona:
  - En dev/test: `RuntimeError`
  - En prod: drop + log-safe

## Event envelope
Todos los eventos `schema_version=1.0` incluyen:
- `emitter="denis_persona"`
- `correlation_id`
- `turn_id`

No se persisten secretos ni prompts crudos (solo hashes + longitudes).

