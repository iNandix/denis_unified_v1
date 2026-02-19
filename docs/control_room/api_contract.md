# Control Room API Contract (WS9)

Goals:
- Graph is the operational SSoT for Task/Approval/Run/Step/Artifact state (no raw payloads).
- WS-first events (`event_v1`) are emitted for all lifecycle transitions.
- Dangerous ops are fail-closed on missing approval (or inability to verify approvals).
- Visibility endpoints are fail-open.

## Feature Flag / Rollback

Disable Control Room:

```bash
export CONTROL_ROOM_ENABLED=0
```

Rollback file surface (optional):
- `api/routes/control_room.py`
- `denis_unified_v1/control_room/`
- `denis_unified_v1/graph/materializers/event_materializer.py`
- `denis_unified_v1/graph/graph_client.py`
- `api/fastapi_server.py`
- `api/routes/telemetry_ops.py`
- `api/routes/health_ops.py`

## HTTP Endpoints

All endpoints are best-effort and must not return HTTP 500 (degrade instead).

### POST `/control_room/task`

Create a task.

Request JSON:
- `type`: string (task type, e.g. `ops_query`, `deploy`, `rollback`)
- `priority`: string or int (normalized into `low|normal|high|critical`)
- `reason_safe`: string (short human-readable reason; no secrets)
- `payload`: object (never stored/emitted raw; only hashed after sanitization)

Response JSON:
- `task_id`: string (sha256)
- `status`: `queued`

### POST `/control_room/task/{task_id}/cancel`

Cancel a task.

Response JSON:
- `task_id`: string
- `status`: `canceled`

### POST `/control_room/approval/{approval_id}/approve`

Approve an approval gate.

Request JSON:
- `resolved_by`: string
- `reason_safe`: string|null

Response JSON:
- `approval_id`: string
- `status`: `approved`

### POST `/control_room/approval/{approval_id}/reject`

Reject an approval gate.

Request/Response same shape as approve, status is `rejected`.

### GET `/control_room/tasks`

Query parameters:
- `status`: string|null
- `type`: string|null
- `limit`: int (max 100)

Response JSON:
- `tasks`: list of Task node dicts (graph-projected)
- `warning`: optional (e.g. `graph_unavailable`)

### GET `/control_room/task/{task_id}`

Response JSON:
- `task_id`: string
- `task`: Task node dict|null
- `runs`: list of Run node dicts
- `steps`: list of Step node dicts
- `warning`: optional

## Event Emission (WS Backbone)

Events are emitted through `api.persona.event_router.persona_emit` and are sanitized before persistence.

Minimum event types used by WS9:
- `control_room.task.created`
- `control_room.task.updated`
- `control_room.run.spawned`
- `control_room.approval.requested`
- `control_room.approval.resolved`
- `run.step` (for ordered steps + artifact pointers + touched components)
