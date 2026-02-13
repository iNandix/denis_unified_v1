"""Phase-8 voice pipeline: STT -> chat -> TTS."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import time
from typing import Any

import aiohttp

from denis_unified_v1.voice.stt_engine import STTEngine
from denis_unified_v1.voice.tts_engine import TTSEngine


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VoicePipelineResult:
    transcribed_text: str
    response_text: str
    tts_audio_base64: str
    provider: str
    latency_stt_ms: int
    latency_llm_ms: int
    latency_tts_ms: int
    latency_total_ms: int
    tts_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "transcribed_text": self.transcribed_text,
            "response_text": self.response_text,
            "tts_audio_base64": self.tts_audio_base64,
            "provider": self.provider,
            "latency_stt_ms": self.latency_stt_ms,
            "latency_llm_ms": self.latency_llm_ms,
            "latency_tts_ms": self.latency_tts_ms,
            "latency_total_ms": self.latency_total_ms,
            "tts_error": self.tts_error,
            "timestamp_utc": _utc_now(),
        }


class VoicePipeline:
    def __init__(self) -> None:
        self.stt = STTEngine()
        self.tts = TTSEngine()
        self.chat_url = (
            os.getenv("DENIS_VOICE_CHAT_URL")
            or os.getenv("DENIS_UNIFIED_CHAT_URL")
            or "http://127.0.0.1:8001/v1/chat/completions"
        ).strip()
        self.chat_stream_url = (
            os.getenv("DENIS_VOICE_CHAT_STREAM_URL") or self.chat_url
        ).strip()
        self.chat_timeout_sec = float(os.getenv("DENIS_VOICE_CHAT_TIMEOUT_SEC", "8.0"))
        self._sentence_split_chars = (".", "?", "!")

    async def process_audio_base64(
        self,
        audio_base64: str,
        *,
        language: str = "es",
        voice: str | None = None,
        model: str = "denis-cognitive",
    ) -> VoicePipelineResult:
        started = time.perf_counter()

        stt_started = time.perf_counter()
        stt_res = await self.stt.transcribe_base64(audio_base64, language=language)
        stt_ms = int((time.perf_counter() - stt_started) * 1000)
        user_text = stt_res.get("text", "").strip()
        if not user_text:
            user_text = "No se detectó texto en audio."

        llm_started = time.perf_counter()
        response_text = await self._chat(user_text=user_text, model=model)
        llm_ms = int((time.perf_counter() - llm_started) * 1000)

        tts_started = time.perf_counter()
        tts_input = self._first_sentence(response_text)
        tts_res = await self.tts.synthesize(tts_input, voice=voice, language=language)
        tts_ms = int((time.perf_counter() - tts_started) * 1000)

        total_ms = int((time.perf_counter() - started) * 1000)
        return VoicePipelineResult(
            transcribed_text=user_text,
            response_text=response_text,
            tts_audio_base64=str(tts_res.get("audio_base64") or ""),
            provider=str(tts_res.get("provider") or "unknown"),
            latency_stt_ms=stt_ms,
            latency_llm_ms=llm_ms,
            latency_tts_ms=tts_ms,
            latency_total_ms=total_ms,
            tts_error=str(tts_res.get("error")) if tts_res.get("error") else None,
        )

    async def _chat(self, user_text: str, model: str) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_text}],
            "stream": False,
        }
        timeout = aiohttp.ClientTimeout(total=max(0.5, self.chat_timeout_sec))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.chat_url, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f"voice_chat_http_{resp.status}:{str(data)[:300]}")
                content = ""
                if isinstance(data, dict):
                    choices = data.get("choices") or []
                    message = choices[0].get("message", {}) if choices else {}
                    content = str(message.get("content") or "").strip()
                    if not content:
                        for key in ("response", "answer", "text", "content"):
                            val = data.get(key)
                            if isinstance(val, str) and val.strip():
                                content = val.strip()
                                break
                return content or "Sin respuesta disponible."

    def _first_sentence(self, text: str) -> str:
        clean = text.strip()
        if not clean:
            return "Sin respuesta disponible."
        for char in self._sentence_split_chars:
            idx = clean.find(char)
            if idx > 0:
                return clean[: idx + 1]
        return clean[:220]

    async def stream_sentences_for_tts(self, full_text: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        current = []
        for char in full_text:
            current.append(char)
            if char in self._sentence_split_chars and len(current) > 8:
                await queue.put("".join(current).strip())
                current = []
        if current:
            await queue.put("".join(current).strip())
        return queue

    async def process_audio_base64_stream(
        self,
        audio_base64: str,
        *,
        language: str = "es",
        voice: str | None = None,
        model: str = "denis-cognitive",
    ):
        started = time.perf_counter()
        stt_started = time.perf_counter()
        stt_res = await self.stt.transcribe_base64(audio_base64, language=language)
        stt_ms = int((time.perf_counter() - stt_started) * 1000)
        user_text = stt_res.get("text", "").strip() or "No se detectó texto en audio."
        yield {
            "type": "stt",
            "text": user_text,
            "latency_stt_ms": stt_ms,
            "timestamp_utc": _utc_now(),
        }

        llm_started = time.perf_counter()
        full_text = ""
        sentence_buffer = []
        seq = 0
        tts_tasks: list[tuple[int, str, asyncio.Task[dict[str, Any]]]] = []
        got_stream_token = False

        timeout = aiohttp.ClientTimeout(total=max(0.5, self.chat_timeout_sec))
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_text}],
            "stream": True,
        }

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.chat_stream_url, json=payload) as resp:
                    if resp.status >= 400:
                        raise RuntimeError(f"voice_chat_stream_http_{resp.status}")
                    async for raw in resp.content:
                        line = raw.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except Exception:
                            continue
                        choices = obj.get("choices") or []
                        delta = choices[0].get("delta", {}) if choices else {}
                        token = str(delta.get("content") or "")
                        if not token:
                            continue
                        got_stream_token = True
                        full_text += token
                        sentence_buffer.append(token)
                        yield {
                            "type": "text_delta",
                            "delta": token,
                            "timestamp_utc": _utc_now(),
                        }
                        if any(ch in token for ch in self._sentence_split_chars):
                            sentence = "".join(sentence_buffer).strip()
                            if sentence:
                                seq += 1
                                task = asyncio.create_task(
                                    self.tts.synthesize(
                                        sentence,
                                        voice=voice,
                                        language=language,
                                    )
                                )
                                tts_tasks.append((seq, sentence, task))
                                yield {
                                    "type": "text_sentence",
                                    "seq": seq,
                                    "text": sentence,
                                    "timestamp_utc": _utc_now(),
                                }
                            sentence_buffer = []
        except Exception:
            full_text = await self._chat(user_text=user_text, model=model)
            yield {
                "type": "text_delta",
                "delta": full_text,
                "timestamp_utc": _utc_now(),
                "source": "fallback_non_stream",
            }
            seq += 1
            task = asyncio.create_task(
                self.tts.synthesize(
                    self._first_sentence(full_text),
                    voice=voice,
                    language=language,
                )
            )
            tts_tasks.append((seq, self._first_sentence(full_text), task))

        if not got_stream_token and not tts_tasks:
            full_text = await self._chat(user_text=user_text, model=model)
            if full_text:
                yield {
                    "type": "text_delta",
                    "delta": full_text,
                    "timestamp_utc": _utc_now(),
                    "source": "non_sse_fallback",
                }
                seq += 1
                sentence = self._first_sentence(full_text)
                yield {
                    "type": "text_sentence",
                    "seq": seq,
                    "text": sentence,
                    "timestamp_utc": _utc_now(),
                }
                task = asyncio.create_task(
                    self.tts.synthesize(sentence, voice=voice, language=language)
                )
                tts_tasks.append((seq, sentence, task))

        if sentence_buffer:
            sentence = "".join(sentence_buffer).strip()
            if sentence:
                seq += 1
                task = asyncio.create_task(
                    self.tts.synthesize(sentence, voice=voice, language=language)
                )
                tts_tasks.append((seq, sentence, task))
                yield {
                    "type": "text_sentence",
                    "seq": seq,
                    "text": sentence,
                    "timestamp_utc": _utc_now(),
                }

        llm_ms = int((time.perf_counter() - llm_started) * 1000)

        for chunk_seq, sentence, task in tts_tasks:
            tts_res = await task
            yield {
                "type": "audio_chunk",
                "seq": chunk_seq,
                "text_seq": chunk_seq,
                "text": sentence,
                "audio_base64": str(tts_res.get("audio_base64") or ""),
                "provider": str(tts_res.get("provider") or "unknown"),
                "tts_error": tts_res.get("error"),
                "timestamp_utc": _utc_now(),
            }

        total_ms = int((time.perf_counter() - started) * 1000)
        yield {
            "type": "done",
            "latency_llm_ms": llm_ms,
            "latency_total_ms": total_ms,
            "response_text": full_text.strip(),
            "timestamp_utc": _utc_now(),
        }


def build_voice_pipeline() -> VoicePipeline:
    return VoicePipeline()
