# WS12-G: Pipecat Voice Graph-First

## Goals
- Create a `VoiceSession` node in Graph at voice session start.
- Emit `voice.*` events over the WS-first Event Bus (`/v1/ws`) with HTTP replay fallback (`/v1/events`).
- Keep Graph/event store free of raw audio blobs and raw text transcripts.
- Provide TTS playback to UI via URL/handle (`voice.tts.audio.ready`).

## Graph Node (minimal)
`VoiceSession` properties:
- `id`: `sha256(conversation_id + ":" + session_ts_ms)`
- `conversation_id`
- `status`: `active|ended|error` (MVP uses `active`, sets `error` on `voice.error`)
- `ts`: ISO timestamp
- `last_event_ts`: ISO timestamp
- `error_count`: integer

Materialization is done by `denis_unified_v1.graph.materializers.event_materializer` from `voice.*` events.

## Event Types
See `docs/schema/event_types_v1.md` for the envelope and payload rules.

Implemented events:
- `voice.session.started`
- `voice.asr.partial` (reserved, optional)
- `voice.asr.final`
- `voice.tts.requested`
- `voice.tts.audio.ready` (contains `handle` + relative `url`)
- `voice.tts.done`
- `voice.error`

## API Endpoints (MVP)
Routes live in `api/routes/voice.py`.

- `POST /v1/voice/session/start`
  - Emits `voice.session.started`
  - Returns `voice_session_id`

- `POST /v1/voice/chat`
  - Accepts either:
    - `text` (fallback path, no STT needed)
    - `audio_base64` (best-effort STT via `DENIS_STT_URL`)
  - Emits:
    - `voice.asr.final`
    - `chat.message` (redacted; role=user)
    - `run.step` (voice_chat RUNNING/SUCCESS)
    - `chat.message` (redacted; role=assistant)
    - `voice.tts.*` (if `tts_enabled=true`)
  - Returns:
    - `assistant_text`
    - `tts.url` (relative URL) when available

- `GET /v1/voice/audio/{handle}.wav`
  - Serves cached WAV for UI playback.

## Fail-Open Behavior
- If STT or TTS backends are missing, the API returns 200 with degraded fields and emits `voice.error`.
- In contract test mode (`ENV!=production` and `DENIS_CONTRACT_TEST_MODE=1`), TTS is synthesized as a deterministic silent WAV.

