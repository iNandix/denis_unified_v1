"""Control Room API -- Task lifecycle, Approvals, and status queries.

Fail-open for reads (visibility). Fail-closed for dangerous mutations (require approval).
Never returns HTTP 500 -- always returns 200 with degraded content on error.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from denis_unified_v1.guardrails.event_payload_policy import sanitize_event_payload

router = APIRouter(prefix="/control_room", tags=["control_room"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _extract_headers(request: Request) -> tuple[str, str]:
    """Extract conversation_id and trace_id from request headers."""
    conversation_id = request.headers.get("x-denis-conversation-id") or "default"
    trace_id = request.headers.get("x-denis-trace-id") or uuid.uuid4().hex
    return conversation_id, trace_id


def _extract_requester(request: Request) -> str:
    """Extract requester identity from request."""
    requester = request.headers.get("x-denis-requester")
    if requester:
        return requester
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _ts_bucket_5m() -> str:
    """Return a 5-minute time bucket string for idempotency."""
    now = int(time.time())
    bucket = now - (now % 300)
    return str(bucket)

def _priority_to_str(priority: Any) -> str:
    """Normalize priority input into low|normal|high|critical."""
    if isinstance(priority, str):
        p = priority.strip().lower()
        if p in {"low", "normal", "high", "critical"}:
            return p
        return "normal"
    try:
        p = int(priority)
    except Exception:
        return "normal"
    # Conventional: 1=critical ... 10=low (fallback).
    if p <= 2:
        return "critical"
    if p <= 4:
        return "high"
    if p <= 7:
        return "normal"
    return "low"


# ---------------------------------------------------------------------------
# POST /control_room/task -- Create a new task
# ---------------------------------------------------------------------------
@router.post("/task")
async def create_task(request: Request) -> JSONResponse:
    """Create a new task in the Control Room.

    Body: { "type": str, "priority": int=5, "budget": dict|None,
            "reason_safe": str|None, "payload": dict|None }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    conversation_id, trace_id = _extract_headers(request)
    requester = _extract_requester(request)

    task_type = str(body.get("type") or "unknown")
    priority_str = _priority_to_str(body.get("priority"))
    budget = body.get("budget")
    reason_safe = body.get("reason_safe") or ""
    payload = body.get("payload")
    specialty = str(body.get("specialty") or "").strip()
    no_overlap_contract_hash = str(body.get("no_overlap_contract_hash") or "").strip()
    requested_paths = body.get("requested_paths")
    if not isinstance(requested_paths, list):
        requested_paths = []
    requested_paths_safe = [str(p)[:200] for p in requested_paths[:50] if isinstance(p, (str, int, float, bool))]

    # Compute payload_redacted_hash (hash of REDACTED payload; never emit/store raw).
    payload_redacted_hash = ""
    if payload and isinstance(payload, dict):
        try:
            payload_safe = sanitize_event_payload(payload).payload
            payload_str = json.dumps(payload_safe, sort_keys=True, ensure_ascii=True)[:20000]
            payload_redacted_hash = _sha256(payload_str)
        except Exception:
            payload_redacted_hash = ""

    # Compute task_id with deterministic hash for idempotency
    ts_bucket = _ts_bucket_5m()
    task_id_raw = f"{task_type}:{requester}:{payload_redacted_hash}:{ts_bucket}"
    task_id = _sha256(task_id_raw)

    ts = _utc_now_iso()

    # Emit event with safe fields only (no raw payload)
    try:
        from api.persona.event_router import persona_emit as emit_event

        emit_event(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="control_room.task.created",
            severity="info",
            ui_hint={"render": "task", "icon": "plus", "collapsible": True},
            payload={
                "task_id": task_id,
                "type": task_type,
                "priority": priority_str,
                "requester": requester,
                "reason_safe": reason_safe,
                "payload_redacted_hash": payload_redacted_hash,
                "created_ts_bucket_5m": ts_bucket,
                "budget_keys": list((budget or {}).keys())[:50],
                "specialty": specialty,
                "no_overlap_contract_hash": no_overlap_contract_hash,
                "requested_paths": requested_paths_safe,
            },
        )
    except Exception:
        pass

    # Best-effort graph upsert
    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        gc.upsert_task(
            task_id=task_id,
            props={
                "type": task_type,
                "priority": priority_str,
                "requester": requester,
                "reason_safe": reason_safe,
                "payload_redacted_hash": payload_redacted_hash,
                "status": "queued",
                "created_ts": ts,
                "conversation_id": conversation_id,
                "trace_id": trace_id,
                "specialty": specialty,
                "no_overlap_contract_hash": no_overlap_contract_hash,
                "requested_paths": requested_paths_safe,
            },
        )
    except Exception:
        pass

    return JSONResponse(
        content={"task_id": task_id, "status": "queued"},
        status_code=200,
    )


# ---------------------------------------------------------------------------
# POST /control_room/task/{task_id}/cancel -- Cancel a task
# ---------------------------------------------------------------------------
@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request) -> JSONResponse:
    """Cancel a task."""
    conversation_id, trace_id = _extract_headers(request)
    ts = _utc_now_iso()

    try:
        from api.persona.event_router import persona_emit as emit_event

        emit_event(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="control_room.task.updated",
            severity="info",
            ui_hint={"render": "task", "icon": "x", "collapsible": True},
            payload={
                "task_id": task_id,
                "status": "canceled",
                "ended_ts": ts,
            },
        )
    except Exception:
        pass

    # Best-effort graph upsert
    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        gc.upsert_task(
            task_id=task_id,
            props={
                "status": "canceled",
                "ended_ts": ts,
                "updated_ts": ts,
            },
        )
    except Exception:
        pass

    return JSONResponse(
        content={"task_id": task_id, "status": "canceled"},
        status_code=200,
    )


# ---------------------------------------------------------------------------
# POST /control_room/approval/{approval_id}/resolve -- Approve or reject
# ---------------------------------------------------------------------------
async def _resolve_approval(approval_id: str, request: Request, *, action: str | None = None) -> JSONResponse:
    """Resolve an approval (approve or reject).

    Body: { "action": "approve"|"reject", "resolved_by": str, "reason_safe": str|None }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    conversation_id, trace_id = _extract_headers(request)

    action = str(action or body.get("action") or "reject")
    resolved_by = str(body.get("resolved_by") or "unknown")
    reason_safe = body.get("reason_safe")

    try:
        from denis_unified_v1.control_room.approvals import resolve_approval

        result = resolve_approval(
            approval_id=approval_id,
            action=action,
            resolved_by=resolved_by,
            reason_safe=reason_safe,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
    except Exception:
        # Fallback: still return a valid response
        action_norm = action.strip().lower()
        if action_norm not in ("approve", "reject"):
            action_norm = "reject"
        result = {
            "approval_id": approval_id,
            "status": action_norm + "d",
        }

    return JSONResponse(
        content={
            "approval_id": approval_id,
            "status": result.get("status", "approved" if action.strip().lower() == "approve" else "rejected"),
        },
        status_code=200,
    )

@router.post("/approval/{approval_id}/resolve")
async def resolve_approval_endpoint(approval_id: str, request: Request) -> JSONResponse:
    return await _resolve_approval(approval_id, request)

@router.post("/approval/{approval_id}/approve")
async def approve_approval_endpoint(approval_id: str, request: Request) -> JSONResponse:
    return await _resolve_approval(approval_id, request, action="approve")

@router.post("/approval/{approval_id}/reject")
async def reject_approval_endpoint(approval_id: str, request: Request) -> JSONResponse:
    return await _resolve_approval(approval_id, request, action="reject")


# ---------------------------------------------------------------------------
# GET /control_room/tasks -- List tasks
# ---------------------------------------------------------------------------
@router.get("/tasks")
async def list_tasks(
    request: Request,
    status: str | None = None,
    type: str | None = None,
    limit: int = 20,
) -> JSONResponse:
    """List tasks. Fail-open: returns empty list with warning if graph is down."""
    conversation_id, trace_id = _extract_headers(request)
    warning: str | None = None
    tasks: list[dict[str, Any]] = []

    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        driver = gc._get_driver()
        if driver is None:
            warning = "graph_unavailable"
        else:
            # Build dynamic Cypher query
            where_clauses = []
            params: dict[str, Any] = {"limit": min(int(limit), 100)}
            if status:
                where_clauses.append("t.status = $status")
                params["status"] = status
            if type:
                where_clauses.append("COALESCE(t.type, t.task_type) = $type")
                params["type"] = type

            where_str = ""
            if where_clauses:
                where_str = "WHERE " + " AND ".join(where_clauses)

            cypher = f"""
                MATCH (t:Task)
                {where_str}
                RETURN t
                ORDER BY t.priority DESC, t.created_ts ASC
                LIMIT $limit
            """

            with driver.session() as session:
                result = session.run(cypher, **params)
                for record in result:
                    node = record["t"]
                    tasks.append(dict(node))
    except Exception:
        warning = "graph_query_failed"

    response: dict[str, Any] = {"tasks": tasks}
    if warning:
        response["warning"] = warning
    return JSONResponse(content=response, status_code=200)


# ---------------------------------------------------------------------------
# GET /control_room/task/{task_id} -- Task detail
# ---------------------------------------------------------------------------
@router.get("/task/{task_id}")
async def get_task_detail(task_id: str, request: Request) -> JSONResponse:
    """Get task detail including linked Run/Steps. Fail-open: returns minimal if graph down."""
    conversation_id, trace_id = _extract_headers(request)
    warning: str | None = None
    task_data: dict[str, Any] | None = None
    runs: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []

    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        driver = gc._get_driver()
        if driver is None:
            warning = "graph_unavailable"
        else:
            with driver.session() as session:
                # Fetch task
                result = session.run(
                    "MATCH (t:Task {id: $task_id}) RETURN t",
                    task_id=task_id,
                )
                record = result.single()
                if record:
                    task_data = dict(record["t"])

                # Fetch linked runs
                result = session.run(
                    """
                    MATCH (t:Task {id: $task_id})-[:SPAWNS]->(r:Run)
                    RETURN r ORDER BY r.started_ts DESC
                    """,
                    task_id=task_id,
                )
                for rec in result:
                    runs.append(dict(rec["r"]))

                # Fetch linked steps from runs
                result = session.run(
                    """
                    MATCH (t:Task {id: $task_id})-[:SPAWNS]->(r:Run)-[:HAS_STEP]->(s:Step)
                    RETURN s ORDER BY s.order ASC
                    """,
                    task_id=task_id,
                )
                for rec in result:
                    steps.append(dict(rec["s"]))
    except Exception:
        warning = "graph_query_failed"

    response: dict[str, Any] = {
        "task_id": task_id,
        "task": task_data,
        "runs": runs,
        "steps": steps,
    }
    if warning:
        response["warning"] = warning
    return JSONResponse(content=response, status_code=200)
