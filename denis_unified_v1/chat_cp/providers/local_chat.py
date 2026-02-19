"""Local fail-open chat provider."""

from __future__ import annotations

import time

from denis_unified_v1.chat_cp.contracts import ChatError, ChatRequest, ChatResponse


class LocalChatProvider:
    provider = "local"

    def __init__(self, model: str = "local_stub") -> None:
        self.model = model

    def is_configured(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        if request.response_format == "json":
            body = {
                "status": "degraded",
                "message": "local fail-open response",
            }
            return ChatResponse(
                text=None,
                json=body,
                provider="local",
                model=self.model,
                usage={"input_tokens": 0, "output_tokens": 0},
                latency_ms=int((time.perf_counter() - started) * 1000),
                success=False,
                error=ChatError(code="fail_open", msg="external providers unavailable", retryable=False),
                trace_id=request.trace_id,
            )

        return ChatResponse(
            text="Denis local fail-open response.",
            json=None,
            provider="local",
            model=self.model,
            usage={"input_tokens": 0, "output_tokens": 0},
            latency_ms=int((time.perf_counter() - started) * 1000),
            success=False,
            error=ChatError(code="fail_open", msg="external providers unavailable", retryable=False),
            trace_id=request.trace_id,
        )
