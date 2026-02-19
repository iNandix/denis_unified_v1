"""WS15 Persona gateway endpoints (minimal).

Persona is the single frontdoor for channels and the only WS event emitter.
These endpoints are intentionally fail-open and may proxy to legacy routes.
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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.persona.event_router import persona_emit


router = APIRouter(prefix="/persona", tags=["persona"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_conv_id(request: Request, payload_conv_id: str | None = None) -> str:
    return (
        (payload_conv_id or "").strip()
        or (request.headers.get("x-denis-conversation-id") or "").strip()
        or (request.query_params.get("conversation_id") or "").strip()
        or "default"
    )


def _safe_trace_id(request: Request, payload_trace_id: str | None = None) -> str:
    return (payload_trace_id or "").strip() or (request.headers.get("x-denis-trace-id") or "").strip() or uuid.uuid4().hex


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _is_contract_mode() -> bool:
    env = (os.getenv("ENV") or "production").strip().lower()
    return env not in {"prod", "production"} and os.getenv("DENIS_CONTRACT_TEST_MODE") == "1"


def _voice_audio_dir() -> Path:
    return Path(os.getenv("DENIS_VOICE_AUDIO_DIR", "./var/voice_audio")).resolve()


def _write_wav_file(*, handle: str, wav_bytes: bytes) -> str:
    d = _voice_audio_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{handle}.wav"
    out.write_bytes(wav_bytes)
    return str(out)


def _deterministic_silence_wav(duration_ms: int = 220, sample_rate: int = 16000) -> bytes:
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
            return _TTSResult(
                ok=False,
                provider=str(res.get("provider") or "unavailable"),
                wav_bytes=b"",
                bytes_len=0,
                error=str(res.get("error") or "tts_no_audio")[:300],
            )
        body = base64.b64decode(b64.encode("ascii"), validate=False)
        return _TTSResult(
            ok=True,
            provider=str(res.get("provider") or "tts"),
            wav_bytes=body,
            bytes_len=len(body),
        )
    except Exception as exc:
        return _TTSResult(ok=False, provider="unavailable", wav_bytes=b"", bytes_len=0, error=str(exc)[:300])


class PersonaChatRequest(BaseModel):
    conversation_id: str | None = None
    trace_id: str | None = None
    text: str = Field(min_length=1)

    model: str = "denis-cognitive"
    max_tokens: int = Field(default=512, ge=1, le=4096)


@router.post("/chat")
async def persona_chat(req: PersonaChatRequest, request: Request) -> JSONResponse:
    """Minimal /persona/chat endpoint (non-streaming).

    Emits `chat.message` events (hashed content) and returns assistant text.
    """
    conv_id = _safe_conv_id(request, req.conversation_id)
    trace_id = _safe_trace_id(request, req.trace_id)
    user_text = (req.text or "").strip()

    # Emit user message (redacted: only hash+len)
    try:
        from api.telemetry_store import sha256_text

        persona_emit(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="chat.message",
            severity="info",
            ui_hint={"render": "chat_bubble", "icon": "message"},
            payload={"role": "user", "content_sha256": sha256_text(user_text), "content_len": len(user_text)},
        )
    except Exception:
        pass

    assistant_text = ""
    openai_result: dict[str, Any] | None = None
    try:
        from api.openai_compatible import ChatCompletionRequest, ChatMessage, DenisRuntime

        runtime = DenisRuntime()
        chat_req = ChatCompletionRequest(
            model=req.model or "denis-cognitive",
            messages=[ChatMessage(role="user", content=user_text)],
            stream=False,
            max_tokens=req.max_tokens,
        )
        openai_result = await runtime.generate(chat_req)
        try:
            assistant_text = str(openai_result["choices"][0]["message"].get("content") or "")
        except Exception:
            assistant_text = ""
        if not assistant_text.strip():
            assistant_text = "Sin respuesta disponible."
    except Exception as exc:
        assistant_text = "Degraded response: persona chat unavailable."
        try:
            persona_emit(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="error",
                severity="warning",
                ui_hint={"render": "error", "icon": "alert"},
                payload={"code": "persona.chat.degraded", "msg": str(exc)[:200]},
            )
        except Exception:
            pass

    # Emit assistant message (hashed)
    try:
        from api.telemetry_store import sha256_text

        persona_emit(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="chat.message",
            severity="info",
            ui_hint={"render": "chat_bubble", "icon": "message"},
            payload={"role": "assistant", "content_sha256": sha256_text(assistant_text), "content_len": len(assistant_text)},
        )
    except Exception:
        pass

    return JSONResponse(
        status_code=200,
        content={
            "ts": _utc_now_iso(),
            "conversation_id": conv_id,
            "trace_id": trace_id,
            "assistant_text": assistant_text,
            "openai": openai_result,
        },
    )


class PersonaVoiceRequest(BaseModel):
    conversation_id: str | None = None
    trace_id: str | None = None
    voice_session_id: str | None = None

    # STUB (WebSpeech): transcript text.
    text: str | None = None

    # Future (Pipecat): optional audio payload.
    audio_base64: str | None = None

    language: str = Field(default="es", min_length=1)
    model: str = "denis-cognitive"

    tts_enabled: bool = True
    tts_voice: str | None = None


@router.post("/voice")
async def persona_voice(req: PersonaVoiceRequest, request: Request) -> JSONResponse:
    """WS17: Voice through Persona (stub WebSpeech now, Pipecat later).

    - Accepts transcript text (fail-open)
    - Emits voice.* events
    - Converts ASR final -> chat.message -> agent runtime
    - Emits voice.tts.* and returns URL/handle when available
    """
    conv_id = _safe_conv_id(request, req.conversation_id)
    trace_id = _safe_trace_id(request, req.trace_id)
    language = (req.language or "es").strip() or "es"

    try:
        from api.telemetry_store import sha256_text
    except Exception:
        import hashlib

        def sha256_text(text: str) -> str:  # type: ignore[no-redef]
            return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()

    # Voice session (graph-compatible). If missing/invalid: create and emit started.
    voice_session_id = (req.voice_session_id or "").strip()
    if not re.fullmatch(r"[a-f0-9]{64}", voice_session_id):
        voice_session_id = ""

    if not voice_session_id:
        session_ts_ms = int(time.time() * 1000)
        try:
            from voice.pipecat_bridge import new_voice_session_id

            voice_session_id = new_voice_session_id(conversation_id=conv_id, session_ts_ms=session_ts_ms)
        except Exception:
            voice_session_id = sha256_text(f"{conv_id}:{session_ts_ms}")

        persona_emit(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="voice.session.started",
            severity="info",
            ui_hint={"render": "voice_session", "icon": "mic", "collapsible": True},
            payload={"voice_session_id": voice_session_id, "status": "active", "ts_ms": int(session_ts_ms)},
        )

    # --- ASR final (stub from browser) ---
    user_text = (req.text or "").strip()
    asr_source = "browser"
    pipecat_enabled = _env_bool("PIPECAT_ENABLED", False)

    if not user_text and (req.audio_base64 or "").strip():
        if pipecat_enabled:
            # Best-effort Pipecat STT bridge (fail-open; never blocks voice).
            try:
                from voice.pipecat_bridge import pipecat_stt_transcribe

                stt_timeout_s = float(os.getenv("PIPECAT_STT_TIMEOUT_SEC", "6.0"))
                stt_res = await pipecat_stt_transcribe(
                    audio_base64=str(req.audio_base64 or ""),
                    language=language,
                    timeout_sec=stt_timeout_s,
                )
                user_text = str((stt_res or {}).get("text") or "").strip()
                asr_source = str((stt_res or {}).get("source") or "pipecat").strip() or "pipecat"
            except Exception as exc:
                persona_emit(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="voice.error",
                    severity="warning",
                    ui_hint={"render": "voice_error", "icon": "alert", "collapsible": True},
                    payload={
                        "voice_session_id": voice_session_id,
                        "code": "asr_failed",
                        "msg": "pipecat_stt_failed",
                        "detail": {"error": str(exc)[:200], "pipecat_enabled": True},
                    },
                )
                user_text = ""
        else:
            # Not wired yet in stub mode; fail-open with explicit error event.
            persona_emit(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="voice.error",
                severity="warning",
                ui_hint={"render": "voice_error", "icon": "alert", "collapsible": True},
                payload={
                    "voice_session_id": voice_session_id,
                    "code": "asr_unavailable",
                    "msg": "audio_asr_unavailable",
                    "detail": {"pipecat_enabled": bool(pipecat_enabled)},
                },
            )
            user_text = ""

    if not user_text:
        # Nothing to do. Fail-open 200.
        return JSONResponse(
            status_code=200,
            content={
                "ts": _utc_now_iso(),
                "conversation_id": conv_id,
                "trace_id": trace_id,
                "voice_session_id": voice_session_id,
                "assistant_text": "",
                "tts": None,
                "degraded": True,
                "error": {"code": "empty_transcript", "msg": "empty_transcript"},
            },
        )

    # Optional safe preview (off by default).
    preview = ""
    if _env_bool("DENIS_VOICE_ALLOW_PREVIEW", False) and not _is_contract_mode():
        preview = user_text.replace("\n", " ").strip()[:80]

    asr_payload: dict[str, Any] = {
        "voice_session_id": voice_session_id,
        "text_sha256": sha256_text(user_text),
        "text_len": int(len(user_text)),
        "language": language,
        "source": asr_source,
    }
    if preview:
        asr_payload["preview"] = preview

    persona_emit(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="voice.asr.final",
        severity="info",
        ui_hint={"render": "voice_asr", "icon": "waveform", "collapsible": True},
        payload=asr_payload,
    )

    # Mirror as chat.message so downstream tooling stays consistent.
    persona_emit(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="chat.message",
        severity="info",
        ui_hint={"render": "chat_bubble", "icon": "message"},
        payload={"role": "user", "content_sha256": sha256_text(user_text), "content_len": int(len(user_text))},
    )
    persona_emit(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="run.step",
        severity="info",
        ui_hint={"render": "step", "icon": "list", "collapsible": True},
        payload={"step_id": "persona_voice", "state": "RUNNING"},
    )

    # WS10-G: Graph-first Intent/Plan/Tasks (fail-open).
    try:
        from denis_unified_v1.graph.graph_intent_plan import create_intent_plan_tasks

        turn_id = (trace_id or "").strip() or uuid.uuid4().hex
        ws10g_result = create_intent_plan_tasks(
            conversation_id=conv_id,
            turn_id=turn_id,
            user_text=user_text,
            modality="voice",
        )
        if ws10g_result.get("success"):
            persona_emit(
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
                persona_emit(
                    conversation_id=conv_id,
                    trace_id=trace_id,
                    type="plan.task.created",
                    severity="info",
                    ui_hint={"render": "task_created", "icon": "task"},
                    payload={"task_id": task_id, "plan_id": ws10g_result.get("plan_id")},
                )
    except Exception:
        pass

    # Agent pipeline (fail-open).
    assistant_text = ""
    chat_error: str | None = None
    try:
        from api.openai_compatible import ChatCompletionRequest, ChatMessage, DenisRuntime

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
        persona_emit(
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
        persona_emit(
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

    persona_emit(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="chat.message",
        severity="info",
        ui_hint={"render": "chat_bubble", "icon": "message"},
        payload={"role": "assistant", "content_sha256": sha256_text(assistant_text), "content_len": int(len(assistant_text))},
    )

    # --- TTS ---
    tts_payload: dict[str, Any] | None = None
    if bool(req.tts_enabled):
        persona_emit(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="voice.tts.requested",
            severity="info",
            ui_hint={"render": "voice_tts", "icon": "speaker", "collapsible": True},
            payload={
                "voice_session_id": voice_session_id,
                "text_sha256": sha256_text(assistant_text),
                "text_len": int(len(assistant_text)),
                "language": language,
            },
        )

        tts_res = await _tts_synthesize(text=assistant_text, voice=req.tts_voice, language=language)
        if tts_res.ok and tts_res.wav_bytes:
            handle = sha256_text(
                f"{voice_session_id}:{trace_id}:{sha256_text(assistant_text)}:{int(time.time() * 1000)}"
            )
            _ = _write_wav_file(handle=handle, wav_bytes=tts_res.wav_bytes)
            audio_url = f"/v1/voice/audio/{handle}.wav"
            persona_emit(
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
            persona_emit(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="voice.tts.done",
                severity="info",
                ui_hint={"render": "voice_tts", "icon": "check", "collapsible": True},
                payload={"voice_session_id": voice_session_id, "handle": handle, "provider": tts_res.provider},
            )
            tts_payload = {
                "handle": handle,
                "url": audio_url,
                "bytes_len": int(tts_res.bytes_len),
                "provider": tts_res.provider,
            }
        else:
            # Stub fallback (dummy handle) for fail-open UI wiring.
            handle = sha256_text(f"{voice_session_id}:{trace_id}:{sha256_text(assistant_text)}:stub")
            audio_url = f"/v1/voice/audio/{handle}.wav"
            persona_emit(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="voice.tts.audio.ready",
                severity="info",
                ui_hint={"render": "voice_audio", "icon": "music", "collapsible": True},
                payload={
                    "voice_session_id": voice_session_id,
                    "handle": handle,
                    "url": audio_url,
                    "bytes_len": 0,
                    "provider": "stub",
                },
            )
            persona_emit(
                conversation_id=conv_id,
                trace_id=trace_id,
                type="voice.tts.done",
                severity="info",
                ui_hint={"render": "voice_tts", "icon": "check", "collapsible": True},
                payload={"voice_session_id": voice_session_id, "handle": handle, "provider": "stub"},
            )
            tts_payload = {"handle": handle, "url": audio_url, "bytes_len": 0, "provider": "stub"}

            persona_emit(
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

    persona_emit(
        conversation_id=conv_id,
        trace_id=trace_id,
        type="run.step",
        severity="info",
        ui_hint={"render": "step", "icon": "list", "collapsible": True},
        payload={"step_id": "persona_voice", "state": "SUCCESS"},
    )

    return JSONResponse(
        status_code=200,
        content={
            "ts": _utc_now_iso(),
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


@router.post("/control_room")
async def persona_control_room_placeholder(request: Request) -> JSONResponse:
    """Placeholder for Control Room proxy through persona."""
    conv_id = _safe_conv_id(request)
    trace_id = _safe_trace_id(request)
    try:
        persona_emit(
            conversation_id=conv_id,
            trace_id=trace_id,
            type="control_room.action.updated",
            severity="warning",
            ui_hint={"render": "task", "icon": "alert"},
            payload={"action": "not_implemented", "status": "degraded"},
        )
    except Exception:
        pass
    return JSONResponse(status_code=200, content={"status": "degraded", "msg": "persona control_room placeholder"})
