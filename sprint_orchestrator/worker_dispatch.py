"""Dispatch worker jobs to direct model APIs or Celery/CrewAI queues."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import time
import asyncio

from .config import SprintOrchestratorConfig
from .event_bus import EventBus, publish_event
from .model_adapter import (
    build_provider_request,
    invoke_provider_request,
    parse_provider_response,
)
from .models import SprintEvent
from .providers import ProviderStatus, merged_env
from .session_store import SessionStore


@dataclass(frozen=True)
class WorkerDispatchResult:
    status: str
    mode: str
    provider: str
    duration_ms: int
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "provider": self.provider,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


def dispatch_worker_task(
    *,
    config: SprintOrchestratorConfig,
    store: SessionStore,
    session_id: str,
    worker_id: str,
    provider_status: ProviderStatus,
    messages: list[dict[str, str]],
    timeout_sec: float = 45.0,
    bus: EventBus | None = None,
) -> WorkerDispatchResult:
    start = time.perf_counter()
    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="worker.dispatch.start",
            message=f"dispatch provider={provider_status.provider} mode={provider_status.mode}",
            payload={
                "provider": provider_status.provider,
                "mode": provider_status.mode,
            },
        ),
        bus,
    )

    try:
        if provider_status.request_format == "celery_task":
            details = _dispatch_celery(config, provider_status, messages)
            status = "ok"
            mode = "celery"
        elif provider_status.request_format == "local_tool":
            # Execute local qcli tool
            from .tool_executor import ToolExecutor
            from .session_store import SessionStore as _SessionStore  # type: ignore

            # Get session store path from config (we need store for events)
            # Since we don't have store directly here, we create a minimal one?
            # Better: pass store as additional arg? But dispatch_worker_task receives store.
            executor = ToolExecutor(config, store, bus)
            # Extract tool arguments from messages (last user message)
            # messages is list of {role, content}. For tool calls, content is JSON
            if not messages:
                raise ValueError("No messages provided for local_tool")
            last_msg = messages[-1]
            if last_msg["role"] != "user":
                raise ValueError("Expected user message for local_tool")
            try:
                # Parse JSON content as tool call arguments
                import json as _json

                args = _json.loads(last_msg["content"])
            except Exception:
                args = {}
            # tool name is the provider
            tool_name = provider_status.provider
            loop = (
                asyncio.get_event_loop() if hasattr(asyncio, "get_event_loop") else None
            )
            if loop and loop.is_running():
                result = loop.run_until_complete(
                    executor.execute(session_id, worker_id, tool_name, args)
                )
            else:
                # Fallback to sync
                result = asyncio.run(
                    executor.execute(session_id, worker_id, tool_name, args)
                )
            details = result
            status = "ok"
            mode = "local_tool"
        elif provider_status.request_format in {
            "openai_chat",
            "anthropic_messages",
            "denis_chat",
        }:
            request = build_provider_request(
                config=config,
                status=provider_status,
                messages=messages,
            )
            response = invoke_provider_request(request, timeout_sec=timeout_sec)
            normalized = parse_provider_response(provider_status, response["data"])
            details = {
                "request": request.as_dict(redact_headers=True),
                "response": {
                    "http_status": response["http_status"],
                    "text": normalized.get("text", "")[:500],
                    "finish_reason": normalized.get("finish_reason"),
                    "input_tokens": normalized.get("input_tokens"),
                    "output_tokens": normalized.get("output_tokens"),
                },
            }
            status = "ok"
            mode = "direct_api"
        else:
            raise RuntimeError(
                f"Unsupported request_format={provider_status.request_format} for provider={provider_status.provider}"
            )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        details = {"error": str(exc)}
        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="worker.dispatch.error",
                message=str(exc)[:400],
                payload={
                    "provider": provider_status.provider,
                    "mode": provider_status.mode,
                },
            ),
            bus,
        )
        result = WorkerDispatchResult(
            status="error",
            mode=provider_status.mode,
            provider=provider_status.provider,
            duration_ms=duration_ms,
            details=details,
        )
        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="worker.dispatch.end",
                message=f"dispatch status=error provider={provider_status.provider}",
                payload=result.as_dict(),
            ),
            bus,
        )
        return result

    duration_ms = int((time.perf_counter() - start) * 1000)
    result = WorkerDispatchResult(
        status=status,
        mode=mode,
        provider=provider_status.provider,
        duration_ms=duration_ms,
        details=details,
    )
    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="worker.dispatch.end",
            message=f"dispatch status={status} provider={provider_status.provider}",
            payload=result.as_dict(),
        ),
        bus,
    )
    return result


def _dispatch_celery(
    config: SprintOrchestratorConfig,
    provider_status: ProviderStatus,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    env = merged_env(config)
    task_name = (env.get("DENIS_SPRINT_CELERY_TASK") or "denis.sprint.execute").strip()
    queue = (
        provider_status.queue
        or (env.get("DENIS_SPRINT_CREW_QUEUE") or "sprint:crewai").strip()
    )
    app_name = (env.get("DENIS_SPRINT_CELERY_APP") or "denis_crew_tasks").strip()

    try:
        from celery import Celery  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"celery_not_available:{exc}") from exc

    redis_url = (env.get("REDIS_URL") or "").strip()
    if not redis_url:
        raise RuntimeError("REDIS_URL is required for celery worker dispatch")

    app = Celery(app_name, broker=redis_url)
    payload = {
        "provider": provider_status.provider,
        "messages": messages,
        "session_id": env.get("USER_ID", "jotah"),
        "requested_at": int(time.time()),
    }
    async_result = app.send_task(task_name, kwargs=payload, queue=queue)
    return {
        "task_name": task_name,
        "queue": queue,
        "task_id": async_result.id,
        "provider": provider_status.provider,
    }
