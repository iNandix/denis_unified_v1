"""Automatic worker dispatch for sprint sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import SprintOrchestratorConfig
from .event_bus import EventBus
from .providers import (
    ProviderStatus,
    load_provider_statuses,
    provider_status_map,
)
from .session_store import SessionStore
from .worker_dispatch import dispatch_worker_task

_DISPATCHABLE_FORMATS = {"openai_chat", "anthropic_messages", "celery_task"}
_FALLBACK_ORDER = [
    "celery_crewai",
    "llama_node1",
    "llama_node2",
    "legacy_core",
    "groq",
    "openrouter",
    "vllm",
    "claude",
]


@dataclass(frozen=True)
class AutoDispatchItem:
    worker_id: str
    assigned_provider: str
    used_provider: str
    status: str
    mode: str
    duration_ms: int
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "assigned_provider": self.assigned_provider,
            "used_provider": self.used_provider,
            "status": self.status,
            "mode": self.mode,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


def _dispatchable(status: ProviderStatus) -> bool:
    return status.configured and status.request_format in _DISPATCHABLE_FORMATS


def _candidate_providers(
    *,
    assigned: str,
    status_map: dict[str, ProviderStatus],
) -> list[ProviderStatus]:
    out: list[ProviderStatus] = []
    seen: set[str] = set()

    def add(provider_id: str) -> None:
        if provider_id in seen:
            return
        candidate = status_map.get(provider_id)
        if candidate is None or not _dispatchable(candidate):
            return
        out.append(candidate)
        seen.add(provider_id)

    add(assigned)
    for provider in _FALLBACK_ORDER:
        add(provider)
    for provider_id, candidate in status_map.items():
        if _dispatchable(candidate):
            add(provider_id)
    return out


def _choose_provider(
    *,
    assigned: str,
    status_map: dict[str, ProviderStatus],
) -> ProviderStatus | None:
    candidates = _candidate_providers(assigned=assigned, status_map=status_map)
    if not candidates:
        return None
    return candidates[0]


def _dispatch_with_fallback(
    *,
    config: SprintOrchestratorConfig,
    store: SessionStore,
    session_id: str,
    worker_id: str,
    assigned_provider: str,
    messages: list[dict[str, str]],
    timeout_sec: float,
    status_map: dict[str, ProviderStatus],
    bus: EventBus | None = None,
) -> tuple[ProviderStatus | None, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for provider in _candidate_providers(assigned=assigned_provider, status_map=status_map):
        dispatched = dispatch_worker_task(
            config=config,
            store=store,
            session_id=session_id,
            worker_id=worker_id,
            provider_status=provider,
            messages=messages,
            timeout_sec=timeout_sec,
            bus=bus,
        )
        attempts.append(
            {
                "provider": provider.provider,
                "status": dispatched.status,
                "mode": dispatched.mode,
                "duration_ms": dispatched.duration_ms,
                "details": dispatched.details,
            }
        )
        if dispatched.status == "ok":
            return provider, {
                "status": dispatched.status,
                "mode": dispatched.mode,
                "duration_ms": dispatched.duration_ms,
                "details": dispatched.details,
                "attempts": attempts,
            }
    return None, {
        "status": "error",
        "mode": "none",
        "duration_ms": 0,
        "details": {"error": "No provider succeeded"},
        "attempts": attempts,
    }


def run_auto_dispatch(
    *,
    config: SprintOrchestratorConfig,
    store: SessionStore,
    session_id: str,
    timeout_sec: float = 45.0,
    only_worker: str | None = None,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    session = store.load_session(session_id)
    assignments = session.get("assignments") or []
    statuses = load_provider_statuses(config)
    status_map = provider_status_map(statuses)

    results: list[AutoDispatchItem] = []
    for assignment in assignments:
        worker_id = str(assignment.get("worker_id") or "")
        if not worker_id:
            continue
        if only_worker and worker_id != only_worker:
            continue

        assigned_provider = str(assignment.get("provider") or "")
        task = str(assignment.get("task") or "").strip()
        role = str(assignment.get("role") or "worker")

        provider = _choose_provider(assigned=assigned_provider, status_map=status_map)
        if provider is None:
            results.append(
                AutoDispatchItem(
                    worker_id=worker_id,
                    assigned_provider=assigned_provider,
                    used_provider="",
                    status="error",
                    mode="none",
                    duration_ms=0,
                    details={"error": "No dispatchable provider configured"},
                )
            )
            continue

        messages = [
            {
                "role": "system",
                "content": "You are a sprint worker executing a concrete engineering task with evidence-first outputs.",
            },
            {
                "role": "user",
                "content": f"role={role}\nworker_id={worker_id}\ntask={task}",
            },
        ]
        used_provider, dispatch_out = _dispatch_with_fallback(
            config=config,
            store=store,
            session_id=session_id,
            worker_id=worker_id,
            assigned_provider=assigned_provider,
            messages=messages,
            timeout_sec=timeout_sec,
            status_map=status_map,
            bus=bus,
        )
        results.append(
            AutoDispatchItem(
                worker_id=worker_id,
                assigned_provider=assigned_provider,
                used_provider=used_provider.provider if used_provider else "",
                status=str(dispatch_out["status"]),
                mode=str(dispatch_out["mode"]),
                duration_ms=int(dispatch_out["duration_ms"]),
                details=dict(dispatch_out["details"]) | {"attempts": dispatch_out["attempts"]},
            )
        )

    total = len(results)
    ok = len([r for r in results if r.status == "ok"])
    error = total - ok

    return {
        "session_id": session_id,
        "total_workers": total,
        "workers_ok": ok,
        "workers_error": error,
        "results": [r.as_dict() for r in results],
    }
