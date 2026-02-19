# Control Room SSoT Graph Contract

This document defines the graph schema extensions for the Control Room subsystem.
All data is materialized from `event_v1` events into Neo4j via the Graph Materialization
Layer (GML). The graph serves as a Single Source of Truth (SSoT) for operational state.

## Principles

- **MERGE-idempotent**: Every write uses Cypher `MERGE`. Reprocessing events is safe.
- **Fail-open**: If Neo4j is unreachable, all operations no-op and return `False`. The pipeline is never blocked.
- **No raw content**: Only hashes, counts, timestamps, statuses, and short safe strings are stored. No prompts, payloads, or secrets.
- **SQLite dedupe**: `mutation_id = sha256(event_id + mutation_kind + stable_key)` prevents duplicate graph mutations.

## Nodes

### Task

Represents a Control Room task queued for execution.

| Property              | Type    | Description                                      |
|-----------------------|---------|--------------------------------------------------|
| `id`                  | string  | Primary key. Unique task identifier.             |
| `status`              | string  | `queued`, `waiting_approval`, `running`, `done`, `failed`, `canceled` |
| `type`                | string  | Task type (e.g. `run_pipeline`, `execute_action`) |
| `priority`            | string  | `low`, `normal`, `high`, `critical`              |
| `requester`           | string  | Who/what requested the task (e.g. `user:alice`)  |
| `payload_redacted_hash` | string | SHA-256 of the redacted payload                 |
| `reason_safe`         | string  | Short human-readable reason (no secrets)         |
| `created_ts`          | string  | ISO 8601 creation timestamp                      |
| `updated_ts`          | string  | ISO 8601 last update timestamp                   |
| `started_ts`          | string  | ISO 8601 execution start timestamp               |
| `ended_ts`            | string  | ISO 8601 execution end timestamp                 |
| `retries`             | integer | Number of retry attempts                         |

### Approval

Represents a human/policy approval gate.

| Property       | Type   | Description                                          |
|----------------|--------|------------------------------------------------------|
| `id`           | string | Primary key. Unique approval identifier.             |
| `status`       | string | `pending`, `approved`, `rejected`, `expired`         |
| `policy_id`    | string | The approval policy governing this gate              |
| `scope`        | string | What the approval covers (e.g. `destructive_write`)  |
| `requested_ts` | string | ISO 8601 request timestamp                           |
| `resolved_by`  | string | Who resolved it (e.g. `user:bob`, `policy:auto_approve`) |
| `resolved_ts`  | string | ISO 8601 resolution timestamp                        |
| `reason_safe`  | string | Short human-readable reason (no secrets)             |

### Action

Represents a concrete action executed within a step.

| Property              | Type   | Description                                    |
|-----------------------|--------|------------------------------------------------|
| `id`                  | string | Primary key. Unique action identifier.         |
| `name`                | string | Human-readable action name                     |
| `tool`                | string | Tool identifier used                           |
| `status`              | string | `pending`, `running`, `success`, `failed`      |
| `args_redacted_hash`  | string | SHA-256 of the redacted arguments              |
| `result_redacted_hash`| string | SHA-256 of the redacted result                 |
| `updated_ts`          | string | ISO 8601 last update timestamp                 |

## Edges

### Task -[:SPAWNS]-> Run

Created when a task spawns a Run for execution.

- Source: `Task` node
- Target: `Run` node
- Cardinality: 1:N (a task can spawn multiple runs, e.g. on retry)

### Task -[:REQUIRES_APPROVAL]-> Approval

Created when a task requires human/policy approval.

- Source: `Task` node
- Target: `Approval` node
- Cardinality: 1:N (a task can have multiple approval gates)

### Approval -[:GOVERNS]-> Run

Created when an approval gate governs an entire run.

- Source: `Approval` node
- Target: `Run` node
- Cardinality: N:1

### Approval -[:GOVERNS]-> Step

Created when an approval gate governs a specific step.

- Source: `Approval` node
- Target: `Step` node
- Cardinality: N:1

### Step -[:HAS_ACTION]-> Action

Created when a step contains actions.

- Source: `Step` node
- Target: `Action` node
- Properties: `order` (integer) - position within the step
- Cardinality: 1:N

### Step -[:TOUCHED]-> Component

Created when a step touches (reads/writes) a component.

- Source: `Step` node
- Target: `Component` node
- Cardinality: N:M

## Event-to-Mutation Mappings

| Event Type                        | Mutation Kind            | Nodes Created/Updated     | Edges Created              |
|-----------------------------------|--------------------------|---------------------------|----------------------------|
| `control_room.task.created`       | `cr_task_created`        | Task (status=queued)      | -                          |
| `control_room.task.updated`       | `cr_task_updated`        | Task (patch)              | -                          |
| `control_room.run.spawned`        | `cr_run_spawned`         | Run (kind=control_room)   | Task-SPAWNS->Run           |
| `control_room.approval.requested` | `cr_approval_requested`  | Approval (status=pending) | Task-REQUIRES_APPROVAL->Approval, Approval-GOVERNS->Run/Step |
| `control_room.approval.resolved`  | `cr_approval_resolved`   | Approval (patch)          | -                          |
| `control_room.action.updated`     | `cr_action_updated`      | Action                    | Step-HAS_ACTION->Action    |

## Invariants

1. **No raw payloads**: Task payloads are stored as `payload_redacted_hash` (SHA-256 only).
   Action arguments and results are stored as `args_redacted_hash` and `result_redacted_hash`.
2. **No secrets**: `reason_safe` fields must contain only human-readable, non-sensitive text.
3. **Idempotent writes**: All graph writes use `MERGE`. The SQLite dedupe layer prevents
   re-executing mutations for already-processed events.
4. **Fail-open**: Graph unavailability never breaks the Control Room pipeline. All graph
   operations return `False` on failure and the caller continues.
5. **Component freshness**: Every successful CR event materialization updates the
   `control_room` Component node's `freshness_ts`.
6. **Required fields**: Events with missing primary keys (`task_id`, `approval_id`,
   `action_id`, `run_id`) return `MappingResult(handled=False)` and are silently skipped.

## Example Cypher Queries

### List all pending approvals for a task

```cypher
MATCH (t:Task {id: $task_id})-[:REQUIRES_APPROVAL]->(a:Approval {status: "pending"})
RETURN a.id, a.policy_id, a.scope, a.requested_ts
```

### Trace a task's full execution graph

```cypher
MATCH (t:Task {id: $task_id})
OPTIONAL MATCH (t)-[:SPAWNS]->(r:Run)
OPTIONAL MATCH (r)-[:HAS_STEP]->(s:Step)
OPTIONAL MATCH (s)-[:HAS_ACTION]->(a:Action)
OPTIONAL MATCH (t)-[:REQUIRES_APPROVAL]->(appr:Approval)
RETURN t, r, s, a, appr
```

### Find all actions for a step

```cypher
MATCH (s:Step {id: $step_id})-[rel:HAS_ACTION]->(a:Action)
RETURN a.id, a.name, a.tool, a.status, rel.order
ORDER BY rel.order
```
