# Event Types v1 (schema_version=1.0)

All stored events share the envelope defined in `docs/schema/event_v1.json`.

Notes:
- No secrets and no raw prompts are persisted. For chat content we store only `sha256` + length.
- `event_id` is monotonic per `conversation_id`.
- `emitter` is always `denis_persona` (Persona frontdoor).
- `correlation_id` and `turn_id` are assigned by Persona (default = `trace_id` when present).
- `channel` tags the event source for UI grouping: `text|voice|control_room|ops|tool|rag|scrape|compiler`.
- `stored` indicates persistence/replay:
  - `stored=true`: persisted in SQLite and replayable (event_id >= 1)
  - `stored=false`: WS-only ephemeral (event_id == 0); clients must not advance replay offsets
- Event payloads are sanitized by guardrails before persistence/broadcast:
  - denied keys are dropped (e.g. `authorization`, `token`, `api_key`, `secret`, `prompt`, `html`, `snippet`)
  - long strings/lists are capped, with a `_guardrails` summary attached when violations occur.

## Channels
Channel tagging is derived from event `type` (unless explicitly overridden by Persona):
- `text`: `chat.message`, `plan.*`
- `voice`: `voice.*`
- `control_room`: `control_room.*`
- `tool`: `tool.*`
- `rag`: `rag.*`
- `scrape`: `scrape.*` / `scraping.*`
- `compiler`: `compiler.*`, `retrieval.*`
- `neuro`: `neuro.*`, `persona.*`
- `ops`: `ops.*`, `agent.*`, `run.step`, `graph.mutation`, `indexing.upsert`, `error`

## compiler.start
Payload (redacted):
- `input_text_sha256`: string
- `input_text_len`: integer
- `mode`: string
- `compiler`: string (e.g. `openai_chat`, `local_v2`)

UI hint:
- `render`: `compiler`
- `icon`: `cpu`

## retrieval.start
Payload (redacted):
- `query_sha256`: string
- `query_len`: integer
- `policy`: object

UI hint:
- `render`: `retrieval`
- `icon`: `search`

## retrieval.result
Payload:
- `graph_count`: integer
- `chunk_ids_count`: integer
- `refs_hash`: string (sha256)
- `warning`: object|null

UI hint:
- `render`: `retrieval`
- `icon`: `list`

## compiler.result
Payload:
- `pick`: string
- `confidence`: number
- `candidates_top3`: array of `{name, score}`
- `prompt_hash_sha256`: string
- `prompt_len`: integer
- `model`: string|null
- `trace_hash`: string (sha256)
- `degraded`: boolean

UI hint:
- `render`: `compiler`
- `icon`: `check`

## compiler.error
Payload:
- `code`: string
- `msg`: string
- `detail`: object|null

UI hint:
- `render`: `error`
- `icon`: `alert`

## chat.message
Payload:
- `role`: `user|assistant|system`
- `content_sha256`: string
- `content_len`: integer

UI hint:
- `render`: `chat_bubble`
- `icon`: `message`

## plan.created
Payload:
- `intent_id`: string|null
- `plan_id`: string|null
- `task_count`: integer

UI hint:
- `render`: `plan_created`
- `icon`: `checklist`

## plan.task.created
Payload:
- `task_id`: string
- `plan_id`: string|null

UI hint:
- `render`: `task_created`
- `icon`: `task`

## voice.session.started
Payload:
- `voice_session_id`: string (sha256)
- `status`: `active|ended|error` (MVP uses `active`)
- `ts_ms`: integer (epoch milliseconds)

Ingress:
- `/persona/voice` (WS17 stub) is the preferred frontdoor for voice.
- `/v1/voice/*` remains as legacy/fallback.

UI hint:
- `render`: `voice_session`
- `icon`: `mic`

## voice.asr.partial
Payload (redacted):
- `voice_session_id`: string
- `text_sha256`: string
- `text_len`: integer
- `language`: string
- `source`: `stt|text|browser` (optional)

UI hint:
- `render`: `voice_asr`
- `icon`: `waveform`

## voice.asr.final
Payload (redacted):
- `voice_session_id`: string
- `text_sha256`: string
- `text_len`: integer
- `language`: string
- `source`: `stt|text|browser`

UI hint:
- `render`: `voice_asr`
- `icon`: `waveform`

## voice.tts.requested
Payload (redacted):
- `voice_session_id`: string
- `text_sha256`: string
- `text_len`: integer
- `language`: string

UI hint:
- `render`: `voice_tts`
- `icon`: `speaker`

## voice.tts.audio.ready
Payload:
- `voice_session_id`: string
- `handle`: string (opaque)
- `url`: string (relative URL for UI playback)
- `bytes_len`: integer
- `provider`: string

UI hint:
- `render`: `voice_audio`
- `icon`: `music`

## voice.tts.done
Payload:
- `voice_session_id`: string
- `handle`: string
- `provider`: string

UI hint:
- `render`: `voice_tts`
- `icon`: `check`

## voice.error
Payload:
- `voice_session_id`: string
- `code`: string
- `msg`: string
- `detail`: object|null

UI hint:
- `render`: `voice_error`
- `icon`: `alert`

## agent.decision_trace_summary
Payload (MVP):
- `blocked`: boolean
- `x_denis_hop`: integer|null
- `path`: string|null
- `engine_id`: string|null
- `llm_used`: string|null
- `latency_ms`: integer|null

UI hint:
- `render`: `decision_trace`
- `icon`: `route`

## agent.reasoning.summary
Payload:
- `adaptive_reasoning`: object (safe summary; no raw chain-of-thought, no secrets)

UI hint:
- `render`: `reasoning_summary`
- `icon`: `brain`

## tool.call
Payload (MVP, redacted):
- `tool_name`: string
- `args_sha256`: string
- `args_len`: integer

UI hint:
- `render`: `tool_call`
- `icon`: `wrench`

## tool.result
Payload (MVP, redacted):
- `tool_name`: string
- `ok`: boolean
- `result_sha256`: string
- `result_len`: integer

UI hint:
- `render`: `tool_result`
- `icon`: `check`

## graph.mutation
Payload (MVP):
- `layer_id`: string|null
- `entity_id`: string|null
- `op`: string
- `after_hash`: string|null
- `idempotency_key`: string|null

UI hint:
- `render`: `graph_mutation`
- `icon`: `graph`

## ops.metric
Payload (MVP):
- `name`: string
- `value`: number
- `unit`: string|null
- `labels`: object|null

UI hint:
- `render`: `metric`
- `icon`: `gauge`

## rag.search.start
Payload:
- `query_sha256`: string
- `query_len`: integer
- `k`: integer
- `filters`: object|null

UI hint:
- `render`: `rag_search`
- `icon`: `search`

## rag.search.result
Payload:
- `selected`: array of `{chunk_id, score}`
- `warning`: object|null

UI hint:
- `render`: `rag_results`
- `icon`: `list`

## rag.context.compiled
Payload:
- `chunks_count`: integer
- `citations`: array of `{chunk_id, hash_sha256}`

UI hint:
- `render`: `rag_context`
- `icon`: `stack`

## indexing.upsert
Payload:
- `kind`: string
- `hash_sha256`: string
- `status`: string

UI hint:
- `render`: `indexing`
- `icon`: `database`

## run.step
Payload (MVP):
- `step_id`: string
- `state`: `QUEUED|RUNNING|SUCCESS|FAILED|STALE`
- `detail`: object|null

UI hint:
- `render`: `step`
- `icon`: `list`

## error
Payload:
- `code`: string
- `msg`: string
- `detail`: object|null

UI hint:
- `render`: `error`
- `icon`: `alert`

## control_room.task.created
Emitted when a new Control Room task is queued for execution.

Payload:
- `task_id`: string (unique identifier)
- `type`: string (task type, e.g. `run_pipeline`, `execute_action`)
- `priority`: string (`low|normal|high|critical`)
- `requester`: string (who/what requested the task)
- `payload_redacted_hash`: string (sha256 of the redacted payload)
- `reason_safe`: string (short human-readable reason, no secrets)

UI hint:
- `render`: `task`
- `icon`: `clipboard`

## control_room.task.updated
Emitted when a Control Room task changes state (started, completed, failed, retried).

Payload:
- `task_id`: string
- `status`: string (`queued|waiting_approval|running|done|failed|canceled`)
- `retries`: integer|null
- `started_ts`: string|null (ISO 8601)
- `ended_ts`: string|null (ISO 8601)

UI hint:
- `render`: `task`
- `icon`: `refresh`

## control_room.run.spawned
Emitted when a Control Room task spawns a Run for execution.

Payload:
- `task_id`: string
- `run_id`: string (the spawned Run identifier)

UI hint:
- `render`: `run`
- `icon`: `play`

## control_room.approval.requested
Emitted when a task or step requires human/policy approval before proceeding.

Payload:
- `approval_id`: string (unique identifier)
- `task_id`: string (parent task)
- `policy_id`: string (the approval policy governing this gate)
- `scope`: string (what the approval covers, e.g. `destructive_write`, `external_call`)
- `run_id`: string|null (if the approval governs a Run)
- `step_id`: string|null (if the approval governs a Step)

UI hint:
- `render`: `approval`
- `icon`: `shield`

## control_room.approval.resolved
Emitted when an approval request is approved, denied, or timed out.

Payload:
- `approval_id`: string
- `status`: string (`approved|rejected|expired`)
- `resolved_by`: string (who resolved it, e.g. `user:alice`, `policy:auto_approve`)
- `resolved_ts`: string (ISO 8601)
- `reason_safe`: string (short human-readable reason, no secrets)

UI hint:
- `render`: `approval`
- `icon`: `check_shield`

## control_room.action.updated
Emitted when an action within a step is created or changes state.

Payload:
- `action_id`: string (unique identifier)
- `step_id`: string|null (parent step)
- `name`: string (human-readable action name)
- `tool`: string (tool identifier used)
- `status`: string (`pending|running|success|failed`)
- `order`: integer|null (position within the step)
- `args_redacted_hash`: string (sha256 of the redacted arguments)
- `result_redacted_hash`: string (sha256 of the redacted result)

UI hint:
- `render`: `action`
- `icon`: `zap`

## neuro.wake.start
Emitted when Denis Persona triggers the WAKE_SEQUENCE to bootstrap/refresh 12 neuro layers.

Payload:
- `ts`: string (ISO 8601)
- `identity_id`: string (e.g. `identity:denis`)

UI hint:
- `render`: `neuro_wake`
- `icon`: `sun`

## neuro.layer.snapshot
Emitted per layer (x12) during WAKE_SEQUENCE. Ephemeral (stored=false).

Payload:
- `layer_index`: integer (1..12)
- `layer_key`: string
- `title`: string
- `freshness_score`: number (0..1)
- `status`: string (`ok|degraded|stale|error`)
- `signals_count`: integer
- `last_update_ts`: string (ISO 8601)

UI hint:
- `render`: `neuro_layer`
- `icon`: `layers`

## neuro.consciousness.snapshot
Emitted after WAKE_SEQUENCE derives ConsciousnessState.

Payload:
- `mode`: string (`awake|focused|idle|degraded`)
- `fatigue_level`: number (0..1)
- `risk_level`: number (0..1)
- `confidence_level`: number (0..1)
- `guardrails_mode`: string (`normal|strict`)
- `memory_mode`: string (`short|balanced|long`)
- `voice_mode`: string (`on|off|stub`)
- `ops_mode`: string (`normal|incident`)
- `last_wake_ts`: string (ISO 8601)
- `last_turn_ts`: string (ISO 8601)
- `ts`: string (ISO 8601)

UI hint:
- `render`: `neuro_consciousness`
- `icon`: `brain`

## neuro.turn.update
Emitted per turn after UPDATE_SEQUENCE refreshes layer freshness.

Payload:
- `layers_summary`: array of `{layer_index, layer_key, freshness_score, status, signals_count}`
- `ts`: string (ISO 8601)

UI hint:
- `render`: `neuro_update`
- `icon`: `refresh`

## neuro.consciousness.update
Emitted per turn after ConsciousnessState is re-derived.

Payload:
- Same fields as `neuro.consciousness.snapshot`

UI hint:
- `render`: `neuro_consciousness`
- `icon`: `brain`

## persona.state.update
Emitted when Denis Persona mode changes (ephemeral, stored=false).

Payload:
- `mode`: string (`awake|focused|idle|degraded`)
- `ts`: string (ISO 8601)

UI hint:
- `render`: `persona_state`
- `icon`: `user`
