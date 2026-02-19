"""Approval management for Control Room tasks.

Creates and resolves approvals. All mutations emit events via the event bus.
Graph is the SSoT; event emission auto-materializes to graph.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_approval(
    *,
    task_id: str,
    policy_id: str,
    scope: str,
    run_id: str,
    step_id: str | None = None,
    conversation_id: str,
    trace_id: str | None,
) -> str:
    """Create a pending approval, emit event, return approval_id.

    The approval is persisted to graph via event materialization.
    """
    ts = _utc_now_iso()
    # Stable id (idempotent across retries/replays).
    # Spec default: sha256(task_id + ":" + policy_id + ":" + scope)
    approval_id = hashlib.sha256(f"{task_id}:{policy_id}:{scope}".encode("utf-8", errors="ignore")).hexdigest()

    # Emit event (auto-materializes to graph)
    try:
        from api.persona.event_router import persona_emit as emit_event

        emit_event(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="control_room.approval.requested",
            severity="warning",
            ui_hint={"render": "approval", "icon": "shield", "collapsible": False},
            payload={
                "approval_id": approval_id,
                "task_id": task_id,
                "policy_id": policy_id,
                "scope": scope,
                "run_id": run_id,
                "step_id": step_id,
                "status": "pending",
                "requested_ts": ts,
            },
        )
    except Exception:
        pass  # fail-open for event emission

    # Best-effort graph upsert (in case materializer is not wired for this event type)
    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        gc.upsert_approval(
            approval_id=approval_id,
            props={
                "task_id": task_id,
                "policy_id": policy_id,
                "scope": scope,
                "run_id": run_id,
                "step_id": step_id or "",
                "status": "pending",
                "requested_ts": ts,
            },
        )
        gc.link_task_approval(task_id=task_id, approval_id=approval_id)
    except Exception:
        pass  # fail-open

    return approval_id


def resolve_approval(
    *,
    approval_id: str,
    action: str,
    resolved_by: str,
    reason_safe: str | None = None,
    conversation_id: str,
    trace_id: str | None,
) -> dict[str, Any]:
    """Resolve an approval (approve or reject). Emits event and updates graph.

    Returns dict with approval_id, status, resolved_by, resolved_ts.
    """
    ts = _utc_now_iso()
    # Normalize action
    action_norm = action.strip().lower()
    if action_norm not in ("approve", "reject"):
        action_norm = "reject"  # fail-closed: invalid action => reject

    status = "approved" if action_norm == "approve" else "rejected"

    result = {
        "approval_id": approval_id,
        "status": status,
        "resolved_by": resolved_by,
        "resolved_ts": ts,
        "reason_safe": reason_safe or "",
    }

    # Emit event
    try:
        from api.persona.event_router import persona_emit as emit_event

        emit_event(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="control_room.approval.resolved",
            severity="info",
            ui_hint={"render": "approval", "icon": "check" if status == "approved" else "x", "collapsible": True},
            payload={
                "approval_id": approval_id,
                "action": action_norm,
                "status": status,
                "resolved_by": resolved_by,
                "reason_safe": reason_safe or "",
                "resolved_ts": ts,
            },
        )
    except Exception:
        pass  # fail-open

    # Best-effort graph update
    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        gc.upsert_approval(
            approval_id=approval_id,
            props={
                "status": status,
                "resolved_by": resolved_by,
                "reason_safe": reason_safe or "",
                "resolved_ts": ts,
            },
        )
    except Exception:
        pass  # fail-open

    return result
