"""DENIS Persona Runtime: Thin handler over unified kernel (scheduler->plan->router)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from denis_unified_v1.kernel.scheduler import get_model_scheduler, InferenceRequest
from denis_unified_v1.inference.router import InferenceRouter
from denis_unified_v1.kernel.engine_registry import get_engine_registry
from denis_unified_v1.kernel.internet_health import get_internet_health
from denis_unified_v1.actions.planner import generate_candidate_plans, select_plan, create_and_save_action_plan_snapshot
from denis_unified_v1.actions.models import Intent_v1
from pathlib import Path


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    group_id: str = "default"


app = FastAPI(title="DENIS Persona Runtime", version="1.1")

router = InferenceRouter()
scheduler = get_model_scheduler()


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """Persona chat: scheduler assigns plan, router executes plan-first."""
    request_id = str(uuid.uuid4())
    text = req.message

    inference_request = InferenceRequest(
        request_id=request_id,
        session_id=f"persona_{req.user_id}_{req.group_id}",
        route_type="fast_talk",
        task_type="chat",
        payload={"max_tokens": 512, "temperature": 0.7},
    )

    plan = scheduler.assign(inference_request)

    messages = [{"role": "user", "content": text}]
    result = await router.route_chat(
        messages=messages,
        request_id=request_id,
        inference_plan=plan,
    )

    return {
        "response": result.get("response", ""),
        "meta": {
            "request_id": request_id,
            "llm_used": result.get("llm_used"),
            "engine_id": result.get("engine_id"),
            "model_selected": result.get("model_selected"),
            "latency_ms": result.get("latency_ms"),
            "input_tokens": result.get("input_tokens"),
            "output_tokens": result.get("output_tokens"),
            "cost_usd": result.get("cost_usd"),
            "fallback_used": result.get("fallback_used"),
            "attempts": result.get("attempts"),
            "degraded": result.get("degraded"),
            "skipped_engines": result.get("skipped_engines"),
            "internet_status": result.get("internet_status"),
        }
    }


@app.get("/meta")
async def meta() -> dict[str, Any]:
    """Health/meta endpoint for ops and debugging."""
    registry = get_engine_registry()
    internet_status = get_internet_health().check()
    allow_boosters = os.getenv("DENIS_ALLOW_BOOSTERS", "1") == "1"
    engines = list(registry.keys())
    locals_count = sum(1 for e in registry.values() if "local" in e.get("tags", []))
    boosters_count = sum(1 for e in registry.values() if "internet_required" in e.get("tags", []))

    return {
        "version": "v1.1",
        "registry_hash": hash(json.dumps(registry, sort_keys=True)),
        "internet_status": internet_status,
        "allow_boosters": allow_boosters,
        "engine_summary": {
            "total": len(engines),
            "locals": locals_count,
            "boosters": boosters_count,
        },
        "uptime_sec": 0,  # TODO: track uptime
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8084)
