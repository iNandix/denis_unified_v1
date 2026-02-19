"""WS12-G Voice endpoints (Pipecat bridge, fail-open).

Goals:
- Emit `voice.*` events to Event Bus v1 (WS-first) with redacted payloads.
- Create/maintain a minimal `VoiceSession` node in Graph via event materializer.
- Provide a URL/handle for TTS audio (no audio blobs in graph/event store).

Fail-open:
- If STT/TTS backends are unavailable, endpoints still return 200 with degraded payloads
  and emit `voice.error` events.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

from api.persona.event_router import persona_emit as emit_event


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _voice_audio_dir() -> Path:
    return Path(os.getenv("DENIS_VOICE_AUDIO_DIR", "./var/voice_audio")).resolve()


def _is_contract_mode() -> bool:
    env = os.getenv("ENV", "production")
    return env != "production" and os.getenv("DENIS_CONTRACT_TEST_MODE") == "1"


def _safe_conv_id(request: Request, payload_conv_id: str | None = None) -> str:
    return (
        (payload_conv_id or "").strip()
        or (request.headers.get("x-denis-conversation-id") or "").strip()
        or (request.query_params.get("conversation_id") or "").strip()
        or "default"
    )


def _safe_trace_id(request: Request, payload_trace_id: str | None = None) -> str:
    return (payload_trace_id or "").strip() or (request.headers.get("x-denis-trace-id") or "").strip() or str(uuid.uuid4())


def _sha256_text(text: str) -> str:
    # Local helper import to keep module import cheap and fail-open.
    try:
        from api.telemetry_store import sha256_text

        return sha256_text(text or "")
    except Exception:
        # Best-effort fallback; stable but not cryptographically guaranteed if hashlib missing.
        import hashlib

        return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _write_wav_file(*, handle: str, wav_bytes: bytes) -> str:
    d = _voice_audio_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{handle}.wav"
    out.write_bytes(wav_bytes)
    return str(out)


def _deterministic_silence_wav(duration_ms: int = 220, sample_rate: int = 16000) -> bytes:
    # Minimal valid WAV for tests/contract mode.
    frames = int(sample_rate * max(1, duration_ms) / 1000.0)
    pcm = b"\x00\x00" * frames  # 16-bit mono silence
    buf = bytearray()
    import io

    with io.BytesIO() as f:
        with wave.open(f, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        buf.extend(f.getvalue())
    return bytes(buf)


@dataclass(frozen=True)
class _TTSResult:
    ok: bool
    provider: str
    wav_bytes: bytes
    bytes_len: int
    error: str | None = None


async def _tts_synthesize(*, text: str, voice: str | None, language: str) -> _TTSResult:
    if _is_contract_mode():
        wav = _deterministic_silence_wav()
        return _TTSResult(ok=True, provider="deterministic", wav_bytes=wav, bytes_len=len(wav))

    try:
        from denis_unified_v1.voice.tts_engine import TTSEngine

        eng = TTSEngine()
        res = await eng.synthesize(text, voice=voice, language=language)
        b64 = str(res.get("audio_base64") or "")
        if not b64:
            return _TTSResult(ok=False, provider=str(res.get("provider") or "unavailable"), wav_bytes=b"", bytes_len=0, error=str(res.get("error") or "tts_no_audio")[:300])
        body = base64.b64decode(b64.encode("ascii"), validate=False)
        return _TTSResult(ok=True, provider=str(res.get("provider") or "tts"), wav_bytes=body, bytes_len=len(body))
    except Exception as exc:
        return _TTSResult(ok=False, provider="unavailable", wav_bytes=b"", bytes_len=0, error=str(exc)[:300])


class VoiceSessionStartRequest(BaseModel):
    conversation_id: str | None = None
    trace_id: str | None = None


class VoiceChatRequest(BaseModel):
    conversation_id: str | None = None
    trace_id: str | None = None
    voice_session_id: str | None = None

    # Fail-open: allow text input fallback (no STT required).
    text: str | None = None

    # Optional audio path (future Pipecat/STT bridge).
    audio_base64: str | None = None
    language: str = Field(default="es", min_length=1)

    model: str = "denis-cognitive"
    tts_enabled: bool = True
    tts_voice: str | None = None


router = APIRouter(prefix="/v1/voice", tags=["voice"])


@router.get("/audio/{handle}.wav")
async def get_tts_audio(handle: str):
    # No auth (LAN/dev). Fail-open: return JSON error instead of 500.
    try:
        # Prevent path tricks; we only serve sha256-like handles.
        if not re.fullmatch(r"[a-f0-9]{64}", (handle or "").strip()):
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "not_found", "msg": "audio_handle_not_found"}},
            )
        p = _voice_audio_dir() / f"{handle}.wav"
        if not p.exists():
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "msg": "audio_handle_not_found"}})
        return FileResponse(path=str(p), media_type="audio/wav", filename=f"{handle}.wav")
    except Exception as exc:
        return JSONResponse(status_code=200, content={"error": {"code": "degraded", "msg": "audio_fetch_failed", "detail": str(exc)[:200]}})


@router.post("/session/start")
async def start_voice_session(req: VoiceSessionStartRequest, request: Request) -> JSONResponse:
    conv_id = _safe_conv_id(request, req.conversation_id)
    trace_id = _safe_trace_id(request, req.trace_id)

    # Stable VoiceSession id per start (sha256(conv:ts_ms)).
    try:
        from voice.pipecat_bridge import new_voice_session_id

        session_ts_ms = int(time.time() * 1000)
        voice_session_id = new_voice_session_id(conversation_id=conv_id, session_ts_ms=session_ts_ms)
    except Exception:
        voice_session_id = _sha256_text(f"{conv_id}:{int(time.time() * 1000)}")
        session_ts_ms = int(time.time() * 1000)

    ev = emit_event(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="voice.session.started",
        severity="info",
        ui_hint={"render": "voice_session", "icon": "mic", "collapsible": True},
        payload={
            "voice_session_id": voice_session_id,
            "status": "active",
            "ts_ms": int(session_ts_ms),
        },
    )
    return JSONResponse(
        status_code=200,
        content={
            "conversation_id": conv_id,
            "trace_id": trace_id,
            "voice_session_id": voice_session_id,
            "event_id": int(ev.get("event_id") or 0),
            "ts": ev.get("ts") or _utc_now_iso(),
            "status": "active",
        },
    )


@router.post("/chat")
async def voice_chat(req: VoiceChatRequest, request: Request) -> JSONResponse:
    conv_id = _safe_conv_id(request, req.conversation_id)
    trace_id = _safe_trace_id(request, req.trace_id)
    language = (req.language or "es").strip() or "es"

    voice_session_id = (req.voice_session_id or "").strip()
    if not voice_session_id:
        # Implicit start (fail-open convenience).
        try:
            from voice.pipecat_bridge import new_voice_session_id

            voice_session_id = new_voice_session_id(conversation_id=conv_id, session_ts_ms=int(time.time() * 1000))
        except Exception:
            voice_session_id = _sha256_text(f"{conv_id}:{int(time.time() * 1000)}")

        emit_event(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="voice.session.started",
            severity="info",
            ui_hint={"render": "voice_session", "icon": "mic", "collapsible": True},
            payload={"voice_session_id": voice_session_id, "status": "active", "ts_ms": int(time.time() * 1000)},
        )

    # --- ASR / Text input ---
    user_text = (req.text or "").strip()
    asr_source = "text"
    if not user_text and (req.audio_base64 or "").strip():
        # Best-effort STT (fail-open).
        try:
            from denis_unified_v1.voice.stt_engine import STTEngine

            asr_source = "stt"
            stt = STTEngine()
            stt_res = await stt.transcribe_base64(str(req.audio_base64), language=language)
            user_text = str(stt_res.get("text") or "").strip()
        except Exception as exc:
            emit_event(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="voice.error",
                severity="warning",
                ui_hint={"render": "voice_error", "icon": "alert", "collapsible": True},
                payload={
                    "voice_session_id": voice_session_id,
                    "code": "asr_failed",
                    "msg": "asr_failed",
                    "detail": {"error": str(exc)[:200], "source": "stt"},
                },
            )
            user_text = ""

    if not user_text:
        user_text = "..."  # fail-open placeholder, avoids downstream errors

    emit_event(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="voice.asr.final",
        severity="info",
        ui_hint={"render": "voice_asr", "icon": "waveform", "collapsible": True},
        payload={
            "voice_session_id": voice_session_id,
            "text_sha256": _sha256_text(user_text),
            "text_len": int(len(user_text)),
            "language": language,
            "source": asr_source,
        },
    )

    # Also emit a chat.message event (redacted) so the downstream tooling stays consistent.
    emit_event(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="chat.message",
        severity="info",
        ui_hint={"render": "chat_bubble", "icon": "message"},
        payload={"role": "user", "content_sha256": _sha256_text(user_text), "content_len": int(len(user_text))},
    )
    emit_event(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="run.step",
        severity="info",
        ui_hint={"render": "step", "icon": "list", "collapsible": True},
        payload={"step_id": "voice_chat", "state": "RUNNING"},
    )

    # WS10-G: Graph-first Intent/Plan/Tasks (fail-open, never blocks voice).
    # Uses the ASR-final text as the user_text input. Graph stores only hashes/previews.
    try:
        from denis_unified_v1.graph.graph_intent_plan import create_intent_plan_tasks

        # WS15/WS10-G: align graph turn_id with persona/event trace_id for correlation.
        turn_id = (trace_id or "").strip() or str(uuid.uuid4())
        ws10g_result = create_intent_plan_tasks(
            conversation_id=conv_id,
            turn_id=turn_id,
            user_text=user_text,
            modality="voice",
        )

        # Emit timeline events (optional; mirrors graph state).
        if ws10g_result.get("success"):
            emit_event(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="plan.created",
                severity="info",
                ui_hint={"render": "plan_created", "icon": "checklist"},
                payload={
                    "intent_id": ws10g_result.get("intent_id"),
                    "plan_id": ws10g_result.get("plan_id"),
                    "task_count": len(ws10g_result.get("task_ids", []) or []),
                },
            )
            for task_id in ws10g_result.get("task_ids", []) or []:
                emit_event(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="plan.task.created",
                    severity="info",
                    ui_hint={"render": "task_created", "icon": "task"},
                    payload={
                        "task_id": task_id,
                        "plan_id": ws10g_result.get("plan_id"),
                    },
                )
    except Exception:
        pass  # fail-open

    assistant_text = ""
    chat_error: str | None = None
    try:
        from api.openai_compatible import DenisRuntime, ChatCompletionRequest, ChatMessage

        runtime = DenisRuntime()
        chat_req = ChatCompletionRequest(
            model=req.model or "denis-cognitive",
            messages=[ChatMessage(role="user", content=user_text)],
            stream=False,
            max_tokens=512,
        )
        timeout_s = float(os.getenv("DENIS_VOICE_CHAT_TIMEOUT_S", "18.0"))
        result = await asyncio.wait_for(runtime.generate(chat_req), timeout=timeout_s)
        try:
            assistant_text = str(result["choices"][0]["message"].get("content") or "")
        except Exception:
            assistant_text = ""
        if not assistant_text.strip():
            assistant_text = "Sin respuesta disponible."
    except asyncio.TimeoutError:
        chat_error = "timeout"
        assistant_text = "Degraded response: chat backend timeout."
        emit_event(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="voice.error",
            severity="warning",
            ui_hint={"render": "voice_error", "icon": "alert", "collapsible": True},
            payload={
                "voice_session_id": voice_session_id,
                "code": "chat_timeout",
                "msg": "chat_timeout",
                "detail": {"timeout_s": float(os.getenv("DENIS_VOICE_CHAT_TIMEOUT_S", "18.0"))},
            },
        )
    except Exception as exc:
        chat_error = str(exc)[:300]
        assistant_text = "Degraded response: chat backend unavailable."
        emit_event(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="voice.error",
            severity="warning",
            ui_hint={"render": "voice_error", "icon": "alert", "collapsible": True},
            payload={
                "voice_session_id": voice_session_id,
                "code": "chat_failed",
                "msg": "chat_failed",
                "detail": {"error": chat_error},
            },
        )

    emit_event(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="chat.message",
        severity="info",
        ui_hint={"render": "chat_bubble", "icon": "message"},
        payload={"role": "assistant", "content_sha256": _sha256_text(assistant_text), "content_len": int(len(assistant_text))},
    )

    # --- TTS ---
    tts_payload: dict[str, Any] | None = None
    if req.tts_enabled:
        emit_event(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="voice.tts.requested",
            severity="info",
            ui_hint={"render": "voice_tts", "icon": "speaker", "collapsible": True},
            payload={
                "voice_session_id": voice_session_id,
                "text_sha256": _sha256_text(assistant_text),
                "text_len": int(len(assistant_text)),
                "language": language,
            },
        )

        tts_res = await _tts_synthesize(text=assistant_text, voice=req.tts_voice, language=language)
        if tts_res.ok and tts_res.wav_bytes:
            handle = _sha256_text(f"{voice_session_id}:{trace_id}:{_sha256_text(assistant_text)}:{int(time.time() * 1000)}")
            _ = _write_wav_file(handle=handle, wav_bytes=tts_res.wav_bytes)
            audio_url = f"/v1/voice/audio/{handle}.wav"
            emit_event(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="voice.tts.audio.ready",
                severity="info",
                ui_hint={"render": "voice_audio", "icon": "music", "collapsible": True},
                payload={
                    "voice_session_id": voice_session_id,
                    "handle": handle,
                    "url": audio_url,
                    "bytes_len": int(tts_res.bytes_len),
                    "provider": tts_res.provider,
                },
            )
            emit_event(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="voice.tts.done",
                severity="info",
                ui_hint={"render": "voice_tts", "icon": "check", "collapsible": True},
                payload={"voice_session_id": voice_session_id, "handle": handle, "provider": tts_res.provider},
            )
            tts_payload = {"handle": handle, "url": audio_url, "bytes_len": int(tts_res.bytes_len), "provider": tts_res.provider}
        else:
            emit_event(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="voice.error",
                severity="warning",
                ui_hint={"render": "voice_error", "icon": "alert", "collapsible": True},
                payload={
                    "voice_session_id": voice_session_id,
                    "code": "tts_failed",
                    "msg": "tts_failed",
                    "detail": {"error": tts_res.error or "tts_failed", "provider": tts_res.provider},
                },
            )

    emit_event(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="run.step",
        severity="info",
        ui_hint={"render": "step", "icon": "list", "collapsible": True},
        payload={"step_id": "voice_chat", "state": "SUCCESS"},
    )

    return JSONResponse(
        status_code=200,
        content={
            "conversation_id": conv_id,
            "trace_id": trace_id,
            "voice_session_id": voice_session_id,
            "language": language,
            "user_text": user_text,
            "assistant_text": assistant_text,
            "tts": tts_payload,
            "degraded": bool(chat_error),
        },
    )
