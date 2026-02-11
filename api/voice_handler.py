"""Voice API routes for phase-8 incremental pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from denis_unified_v1.voice.audio_stream import AudioChunk
from denis_unified_v1.voice.voice_pipeline import build_voice_pipeline


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VoiceRequest(BaseModel):
    audio_base64: str = Field(min_length=1)
    language: str = "es"
    voice: str | None = None
    model: str = "denis-cognitive"


def build_voice_router() -> APIRouter:
    router = APIRouter(prefix="/v1/voice", tags=["voice"])
    pipeline = build_voice_pipeline()

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "denis_unified_v1_voice_pipeline",
            "timestamp_utc": _utc_now(),
        }

    @router.post("/process")
    async def process_voice(req: VoiceRequest) -> dict[str, Any]:
        result = await pipeline.process_audio_base64(
            req.audio_base64,
            language=req.language,
            voice=req.voice,
            model=req.model,
        )
        return result.as_dict()

    @router.websocket("/stream")
    async def stream_voice(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                payload = await websocket.receive_json()
                audio_base64 = str(payload.get("audio_base64") or "").strip()
                if not audio_base64:
                    await websocket.send_json(
                        {"type": "error", "error": "audio_base64 required"}
                    )
                    continue

                language = str(payload.get("language") or "es")
                voice = payload.get("voice")
                model = str(payload.get("model") or "denis-cognitive")
                async for event in pipeline.process_audio_base64_stream(
                    audio_base64,
                    language=language,
                    voice=voice,
                    model=model,
                ):
                    if event.get("type") == "audio_chunk":
                        chunk = AudioChunk(
                            seq=int(event.get("seq") or 0),
                            audio_base64=str(event.get("audio_base64") or ""),
                        )
                        frame = chunk.as_event()
                        frame["text_seq"] = event.get("text_seq")
                        frame["text"] = event.get("text")
                        frame["provider"] = event.get("provider")
                        frame["tts_error"] = event.get("tts_error")
                        await websocket.send_json(frame)
                    else:
                        await websocket.send_json(event)
        except WebSocketDisconnect:
            return

    return router
