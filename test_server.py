#!/usr/bin/env python3
"""Simple test server for Unified V1 FastAPI."""

import time
from fastapi import FastAPI

app = FastAPI(title="Denis Unified V1 Test", version="1.0.0")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "unified-v1",
        "timestamp": int(time.time()),
        "components": {
            "router": "cognitive_router",
            "smx_phase12": "enabled_or_disabled_flag",
        },
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: dict):
    return {
        "id": "test-123",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.get("model", "denis-unified-v1"),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hola! Soy Denis Unified V1 funcionando correctamente."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting test server on port 8085...")
    uvicorn.run(app, host="0.0.0.0", port=8085)
