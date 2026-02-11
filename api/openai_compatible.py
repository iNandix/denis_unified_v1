"""OpenAI-compatible chat endpoints for Denis incremental API layer."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import uuid
from typing import Any

import aiohttp
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from denis_unified_v1.api.sse_handler import stream_text_chunks


def _utc_now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "denis-cognitive"
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class DenisRuntime:
    def __init__(self) -> None:
        self.models = [
            {"id": "denis-cognitive", "object": "model", "owned_by": "denis"},
            {"id": "denis-fast", "object": "model", "owned_by": "denis"},
            {"id": "denis-core-8084", "object": "model", "owned_by": "denis"},
        ]
        self.legacy_chat_url = (
            os.getenv("DENIS_CORE_CHAT_URL")
            or os.getenv("DENIS_CORE_URL")
            or "http://127.0.0.1:8084/v1/chat"
        ).strip()
        self.legacy_timeout_sec = float(os.getenv("DENIS_CORE_TIMEOUT_SEC", "6.0"))

    async def _try_legacy_chat(self, user_text: str) -> str | None:
        payload = {"message": user_text}
        timeout = aiohttp.ClientTimeout(total=self.legacy_timeout_sec)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.legacy_chat_url, json=payload) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    if isinstance(data, dict):
                        for key in ("response", "answer", "text", "content"):
                            val = data.get(key)
                            if isinstance(val, str) and val.strip():
                                return val.strip()
                    return None
        except Exception:
            return None

    def _extract_user_text(self, messages: list[ChatMessage]) -> str:
        for msg in reversed(messages):
            if msg.role == "user" and isinstance(msg.content, str):
                return msg.content.strip()
        return ""

    def _maybe_tool_call(self, req: ChatCompletionRequest, user_text: str) -> dict[str, Any] | None:
        if not req.tools:
            return None
        lowered = user_text.lower()
        if "tool" not in lowered and "perceive" not in lowered and "act" not in lowered:
            return None
        first = req.tools[0]
        fn = (first.get("function") or {}) if isinstance(first, dict) else {}
        fn_name = fn.get("name") if isinstance(fn, dict) else "denis_tool"
        return {
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": str(fn_name), "arguments": "{}"},
        }

    async def generate(self, req: ChatCompletionRequest) -> dict[str, Any]:
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        user_text = self._extract_user_text(req.messages)

        tool_call = self._maybe_tool_call(req, user_text)
        if tool_call:
            return {
                "id": completion_id,
                "object": "chat.completion",
                "created": _utc_now(),
                "model": req.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": None, "tool_calls": [tool_call]},
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": max(1, len(user_text.split())), "completion_tokens": 0, "total_tokens": max(1, len(user_text.split()))},
                "meta": {"path": "tool_calls"},
            }

        legacy = await self._try_legacy_chat(user_text)
        if legacy:
            answer = legacy
            path = "legacy_8084"
        else:
            answer = (
                f"Denis (incremental API) recibió: '{user_text}'. "
                "Respuesta local porque el core legacy no devolvió contenido."
            )
            path = "local_fallback"

        completion_tokens = max(1, len(answer.split()))
        prompt_tokens = max(1, len(user_text.split()))
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": _utc_now(),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "meta": {"path": path},
        }


def build_openai_router(runtime: DenisRuntime) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["openai"])

    @router.get("/models")
    async def list_models() -> dict[str, Any]:
        return {"object": "list", "data": runtime.models}

    @router.post("/chat/completions")
    async def chat_completions(req: ChatCompletionRequest):
        result = await runtime.generate(req)
        if not req.stream:
            return JSONResponse(result)

        text = ""
        choices = result.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            text = str(msg.get("content") or "")

        async def _gen():
            async for event in stream_text_chunks(
                completion_id=str(result.get("id")),
                model=str(result.get("model", req.model)),
                content=text,
            ):
                yield event
                await asyncio.sleep(0)

        return StreamingResponse(_gen(), media_type="text/event-stream")

    return router

