"""SSE helpers for chat streaming responses."""

from __future__ import annotations

import json
from typing import AsyncIterator


def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=True)}\n\n"


async def stream_text_chunks(
    *,
    completion_id: str,
    model: str,
    content: str,
) -> AsyncIterator[str]:
    words = content.split()
    for token in words:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": f"{token} "},
                    "finish_reason": None,
                }
            ],
        }
        yield sse_event(payload)

    final_payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield sse_event(final_payload)
    yield "data: [DONE]\n\n"

