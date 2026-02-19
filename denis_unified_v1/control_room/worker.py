"""Control Room worker (WS9) — graph-native Task/Approval/Run/Step execution.

Core invariants:
- Graph is SSoT for operational state (Task/Approval/Run/Step/Artifact/Source).
- WS-first events (`event_v1`) are emitted for every lifecycle transition.
- Safe ops: best-effort visibility should be fail-open.
- Dangerous ops: execution is fail-closed if approvals cannot be verified (or graph unavailable).

This worker intentionally performs placeholder step execution (no real tool calls yet).
It still produces deterministic Run/Step ids and materializes Step/Artifact/Component edges via events.
"""

from __future__ import annotations

import hashlib
import os
import socket
import time
from datetime import datetime, timezone
from typing import Any

from denis_unified_v1.control_room.approvals import create_approval
from denis_unified_v1.control_room.graph_repo import (
    ControlRoomGraphRepo,
    GraphUnavailable,
    InMemoryControlRoomGraphRepo,
    TaskRecord,
)
from denis_unified_v1.control_room.policies import get_policy_id, requires_approval
from denis_unified_v1.control_room.task_planner import StepDef, plan_steps
from denis_unified_v1.control_room.worker_state import update_worker_state
from denis_unified_v1.graph.graph_client import get_graph_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _emit(
    *,
    conversation_id: str,
    trace_id: str | None,
    type: str,
    severity: str = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    """Emit event, fail-open."""
    try:
        from api.persona.event_router import persona_emit as emit_event

        emit_event(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type=type,
            severity=severity,
            payload=payload or {},
        )
    except Exception:
        return


def _component_for_tool(tool: str | None) -> str:
    t = (tool or "").strip().lower()
    if t.startswith("neo4j."):
        return "graph_ssot"
    if t.startswith("qdrant.") or t.startswith("vectorstore."):
        return "vectorstore_qdrant"
    if t.startswith("indexing."):
        return "indexing"
    if t.startswith("scraper.") or t.startswith("scraping."):
        return "advanced_scraping"
    if t.startswith("deploy.") or t.startswith("preflight.") or t.startswith("monitor."):
        return "control_room"
    return "control_room"


class ControlRoomWorker:
    """Background worker that polls the graph for pending tasks and executes them."""

    def __init__(
        self, *, repo: Any | None = None, worker_id: str | None = None, specialty: str | None = None
    ) -> None:
        self.enabled = (os.getenv("CONTROL_ROOM_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        self.worker_id = (
            worker_id or os.getenv("CONTROL_ROOM_WORKER_ID") or ""
        ).strip() or _sha256(f"{socket.gethostname()}:{os.getpid()}")[:12]
        self.specialty = (specialty or os.getenv("CONTROL_ROOM_SPECIALTY") or "").strip()
        self.max_tasks_per_tick = int(os.getenv("CONTROL_ROOM_MAX_TASKS_PER_TICK") or "10")
        self.max_retries = int(os.getenv("CONTROL_ROOM_MAX_RETRIES") or "3")
        self.backoff_base_s = float(os.getenv("CONTROL_ROOM_RETRY_BACKOFF_BASE_S") or "1.0")
        self.backoff_max_s = float(os.getenv("CONTROL_ROOM_RETRY_BACKOFF_MAX_S") or "60.0")

        # Repo can be injected for tests/smoke.
        self.repo = repo or ControlRoomGraphRepo()

    def tick(self) -> dict[str, Any]:
        """Execute one worker cycle. Returns status dict."""
        update_worker_state(heartbeat=True, last_tick=True, queue_depth=0, running_count=0)
        if not self.enabled:
            return {"processed": 0, "errors": 0, "skipped_reason": "disabled"}

        now_epoch = int(time.time())
        try:
            try:
                tasks = self.repo.list_tasks_for_worker(
                    now_epoch=now_epoch,
                    limit=self.max_tasks_per_tick,
                    specialty=self.specialty or None,
                )
            except TypeError:
                # Back-compat for injected repos in tests.
                tasks = self.repo.list_tasks_for_worker(
                    now_epoch=now_epoch, limit=self.max_tasks_per_tick
                )
        except GraphUnavailable:
            # Fail-open for visibility, but no execution possible without graph.
            update_worker_state(error=True, queue_depth=0, running_count=0)
            return {"processed": 0, "errors": 1, "skipped_reason": "graph_unavailable"}

        update_worker_state(queue_depth=len(tasks), running_count=0)
        processed = 0
        errors = 0

        for task in tasks:
            try:
                # First: respect cancellation.
                if self._is_canceled(task.id):
                    continue
                # Specialty isolation (skip if repo didn't filter).
                if (
                    self.specialty
                    and (task.specialty or "")
                    and str(task.specialty) != str(self.specialty)
                ):
                    continue

                # Resume waiting approvals when approved.
                if task.status == "waiting_approval":
                    if self._approval_status(task, scope=task.type) == "approved":
                        # Release claim so the queued task can be claimed atomically again.
                        self.repo.patch_task(
                            task.id, {"status": "queued", "claimed_by": "", "claimed_ts": ""}
                        )
                        # Execute in the same tick (tests + lower latency).
                        try:
                            task = self.repo.get_task(task.id) or task
                        except Exception:
                            pass
                    else:
                        continue

                # Execute queued tasks.
                if task.status == "queued":
                    if not self._validate_no_overlap_contract(task):
                        continue
                    if not self._try_claim(task):
                        continue
                    update_worker_state(running_count=1)
                    self._execute_task(task)
                    processed += 1
                update_worker_state(running_count=0)
            except Exception:
                errors += 1
                update_worker_state(error=True, running_count=0)
                try:
                    self._handle_failure(task)
                except Exception:
                    pass

        return {"processed": processed, "errors": errors}

    def _try_claim(self, task: TaskRecord) -> bool:
        """Claim task (graph-centric lock). Fail-open if repo doesn't support claims."""
        try:
            fn = getattr(self.repo, "try_claim_task", None)
            if not callable(fn):
                return True
            ok = bool(fn(task_id=task.id, worker_id=self.worker_id))
            if ok:
                _emit(
                    conversation_id=task.conversation_id or "default",
                    trace_id=task.trace_id or None,
                    type="control_room.task.updated",
                    payload={
                        "task_id": task.id,
                        "claimed_by": self.worker_id,
                        "claimed_ts": _utc_now_iso(),
                    },
                )
            return ok
        except GraphUnavailable:
            return False
        except Exception:
            return False

    def _validate_no_overlap_contract(self, task: TaskRecord) -> bool:
        """Validate specialty ownership contract (dangerous ops fail-closed).

        WS11-G: Verifies:
        1. Worker specialty matches task specialty
        2. Contract hash matches (if present)
        3. Requested paths are within specialty ownership
        """
        if not self.specialty:
            return True

        # WS11-G: Verify worker specialty matches task specialty
        task_specialty = (task.specialty or "").strip().lower()
        worker_specialty = self.specialty.strip().lower()
        if task_specialty and task_specialty != worker_specialty:
            _emit(
                conversation_id=task.conversation_id or "default",
                trace_id=task.trace_id or None,
                type="ops.metric",
                severity="warning",
                payload={
                    "name": "control_room.specialty_mismatch",
                    "value": 1,
                    "tags": {"worker": worker_specialty, "task": task_specialty},
                },
            )
            return False

        requested = list(task.requested_paths or ())
        contract_hash = (task.no_overlap_contract_hash or "").strip()
        if not requested and not contract_hash:
            return True

        try:
            from denis_unified_v1.control_room.specialties import get_specialty

            spec = get_specialty(self.specialty)
        except Exception:
            # Unknown specialty: fail-closed if task expects isolation.
            self.repo.patch_task(
                task.id,
                {
                    "status": "failed",
                    "ended_ts": _utc_now_iso(),
                    "reason_safe": "unknown_specialty",
                },
            )
            _emit(
                conversation_id=task.conversation_id or "default",
                trace_id=task.trace_id or None,
                type="ops.metric",
                severity="critical",
                payload={
                    "name": "control_room.no_overlap_violation",
                    "value": 1,
                    "tags": {"reason": "unknown_specialty"},
                },
            )
            return False

        if contract_hash and contract_hash != spec.no_overlap_contract_hash:
            self.repo.patch_task(
                task.id,
                {
                    "status": "failed",
                    "ended_ts": _utc_now_iso(),
                    "reason_safe": "no_overlap_contract_mismatch",
                },
            )
            _emit(
                conversation_id=task.conversation_id or "default",
                trace_id=task.trace_id or None,
                type="ops.metric",
                severity="critical",
                payload={
                    "name": "control_room.no_overlap_violation",
                    "value": 1,
                    "tags": {"reason": "contract_mismatch"},
                },
            )
            return False

        if requested and not spec.allows_paths(requested):
            self.repo.patch_task(
                task.id,
                {
                    "status": "failed",
                    "ended_ts": _utc_now_iso(),
                    "reason_safe": "no_overlap_path_violation",
                },
            )
            _emit(
                conversation_id=task.conversation_id or "default",
                trace_id=task.trace_id or None,
                type="ops.metric",
                severity="critical",
                payload={
                    "name": "control_room.no_overlap_violation",
                    "value": 1,
                    "tags": {"reason": "path_violation"},
                },
            )
            return False

        return True

    def _is_canceled(self, task_id: str) -> bool:
        try:
            t = self.repo.get_task(task_id)
            return bool(t and t.status == "canceled")
        except Exception:
            return False

    def _approval_status(self, task: TaskRecord, *, scope: str) -> str:
        """Return latest approval status for a task+scope, or 'none'."""
        try:
            a = self.repo.get_latest_approval_for_task(task_id=task.id, scope=str(scope))
        except GraphUnavailable:
            return "none"
        if not a:
            return "none"
        return (a.status or "").strip().lower() or "none"

    def _ensure_approval_or_wait(
        self,
        *,
        task: TaskRecord,
        conversation_id: str,
        trace_id: str | None,
        scope: str,
        governs_run_id: str,
        governs_step_id: str | None = None,
    ) -> bool:
        """Ensure approval exists+approved. If missing/pending -> request and set waiting_approval."""
        st = self._approval_status(task, scope=scope)
        if st == "approved":
            return True
        if st in {"rejected", "expired"}:
            # Fail-closed: do not execute once explicitly rejected/expired.
            self.repo.patch_task(
                task.id,
                {"status": "failed", "ended_ts": _utc_now_iso(), "updated_ts": _utc_now_iso()},
            )
            return False

        # Missing or pending: request if missing, and wait.
        if st == "none":
            policy_id = get_policy_id(task.type)
            approval_id = create_approval(
                task_id=task.id,
                policy_id=policy_id,
                scope=str(scope),
                run_id=governs_run_id,
                step_id=governs_step_id,
                conversation_id=conversation_id,
                trace_id=trace_id,
            )
            # If using in-memory repo, mirror approval to allow tests to resolve.
            if isinstance(self.repo, InMemoryControlRoomGraphRepo):
                self.repo.put_approval(
                    approval={
                        "id": approval_id,
                        "status": "pending",
                        "policy_id": policy_id,
                        "scope": str(scope),
                        "requested_ts": _utc_now_iso(),
                    },
                    task_id=task.id,
                )

        # Release any previous claim while waiting for approval.
        self.repo.patch_task(
            task.id, {"status": "waiting_approval", "claimed_by": "", "claimed_ts": ""}
        )
        _emit(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="control_room.task.updated",
            payload={
                "task_id": task.id,
                "status": "waiting_approval",
                "reason_safe": "requires_approval",
            },
        )
        return False

    def _execute_task(self, task: TaskRecord) -> None:
        task_id = task.id
        task_type = task.type

        # These identifiers are intentionally "pointers only" for graph. Do not store raw payloads.
        conversation_id = task.conversation_id or "default"
        trace_id = task.trace_id or None

        run_id = _sha256(f"control_room:{task_id}")

        # WS11-G: Persist Run node in Graph (SSoT).
        self._persist_run_to_graph(
            run_id=run_id,
            task_id=task_id,
            task_type=task_type,
            conversation_id=conversation_id,
            trace_id=trace_id,
            specialty=task.specialty,
        )

        # Dangerous tasks (and unknown) always require approval. Fail-closed if graph cannot verify.
        task_level_approved = False
        if requires_approval(task_type):
            if not self._ensure_approval_or_wait(
                task=task,
                conversation_id=conversation_id,
                trace_id=trace_id,
                scope=task_type,
                governs_run_id=run_id,
            ):
                return
            task_level_approved = True

        started_ts = _utc_now_iso()
        self.repo.patch_task(task_id, {"status": "running", "started_ts": started_ts})
        _emit(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="control_room.task.updated",
            payload={"task_id": task_id, "status": "running", "started_ts": started_ts},
        )

        _emit(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="control_room.run.spawned",
            payload={"task_id": task_id, "run_id": run_id},
        )

        steps = plan_steps(task_type)
        for step_def in steps:
            # Cancel check (fail-open best-effort).
            if self._is_canceled(task_id):
                ended_ts = _utc_now_iso()
                self.repo.patch_task(task_id, {"status": "canceled", "ended_ts": ended_ts})
                _emit(
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                    type="control_room.task.updated",
                    payload={"task_id": task_id, "status": "canceled", "ended_ts": ended_ts},
                )
                return

            step_id = _sha256(f"{run_id}:{step_def.order}:{step_def.name}")

            # Step-level approval gate (if plan marks it).
            if step_def.requires_approval and not task_level_approved:
                step_scope = f"{task_type}:{step_def.name}"
                if not self._ensure_approval_or_wait(
                    task=task,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                    scope=step_scope,
                    governs_run_id=run_id,
                    governs_step_id=step_id,
                ):
                    return

            self._emit_step(
                conversation_id=conversation_id,
                trace_id=trace_id,
                run_id=run_id,
                step_id=step_id,
                step_def=step_def,
                state="RUNNING",
            )

            # Placeholder execution (no tool calls). Still produce an artifact pointer for the graph.
            time.sleep(0.0)

            self._emit_step(
                conversation_id=conversation_id,
                trace_id=trace_id,
                run_id=run_id,
                step_id=step_id,
                step_def=step_def,
                state="SUCCESS",
            )

        ended_ts = _utc_now_iso()
        self.repo.patch_task(
            task_id, {"status": "done", "ended_ts": ended_ts, "next_attempt_epoch": None}
        )
        _emit(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="control_room.task.updated",
            payload={"task_id": task_id, "status": "done", "ended_ts": ended_ts, "run_id": run_id},
        )

    def _emit_step(
        self,
        *,
        conversation_id: str,
        trace_id: str | None,
        run_id: str,
        step_id: str,
        step_def: StepDef,
        state: str,
    ) -> None:
        component_id = _component_for_tool(step_def.tool)
        artifact_id = _sha256(f"{step_id}:{state}")
        counts = {"state": state, "tool": step_def.tool or "", "ok": 1 if state == "SUCCESS" else 0}
        _emit(
            conversation_id=conversation_id,
            trace_id=trace_id,
            type="run.step",
            payload={
                "run_id": run_id,
                "step_id": step_id,
                "name": step_def.name,
                "tool": step_def.tool or "",
                "order": int(step_def.order),
                "state": state,
                "component_id": component_id,
                "artifact_id": artifact_id if state == "SUCCESS" else "",
                "artifact_kind": "step_outcome",
                "counts": counts,
            },
        )

        # WS11-G: Persist Step node and edge to Run in Graph (SSoT).
        self._persist_step_to_graph(
            run_id=run_id,
            step_id=step_id,
            step_def=step_def,
            state=state,
            conversation_id=conversation_id,
        )

    def _persist_run_to_graph(
        self,
        *,
        run_id: str,
        task_id: str,
        task_type: str,
        conversation_id: str,
        trace_id: str | None,
        specialty: str,
    ) -> None:
        """WS11-G: Persist Run node in Graph."""
        try:
            gc = get_graph_client()
            if not gc.enabled:
                return
            gc.upsert_run(
                run_id=run_id,
                props={
                    "task_id": task_id,
                    "task_type": task_type,
                    "conversation_id": conversation_id,
                    "trace_id": trace_id or "",
                    "specialty": specialty,
                    "status": "running",
                },
            )
        except Exception:
            pass

    def _persist_step_to_graph(
        self,
        *,
        run_id: str,
        step_id: str,
        step_def: StepDef,
        state: str,
        conversation_id: str,
    ) -> None:
        """WS11-G: Persist Step node and link to Run in Graph."""
        try:
            gc = get_graph_client()
            if not gc.enabled:
                return

            status = (
                "success" if state == "SUCCESS" else "running" if state == "RUNNING" else "failed"
            )

            gc.upsert_step(
                step_id=step_id,
                props={
                    "run_id": run_id,
                    "name": step_def.name,
                    "tool": step_def.tool or "",
                    "order": int(step_def.order),
                    "status": status,
                    "conversation_id": conversation_id,
                },
            )

            gc.link_run_step(run_id=run_id, step_id=step_id, order=int(step_def.order))
        except Exception:
            pass

    def _handle_failure(self, task: TaskRecord) -> None:
        now = int(time.time())
        retries = int(task.retries or 0) + 1
        if retries > self.max_retries:
            ended_ts = _utc_now_iso()
            self.repo.patch_task(
                task.id, {"status": "failed", "retries": retries, "ended_ts": ended_ts}
            )
            _emit(
                conversation_id=task.conversation_id or "default",
                trace_id=task.trace_id or None,
                type="control_room.task.updated",
                severity="critical",
                payload={
                    "task_id": task.id,
                    "status": "failed",
                    "retries": retries,
                    "ended_ts": ended_ts,
                },
            )
            return

        delay = min(self.backoff_max_s, self.backoff_base_s * (2 ** max(0, retries - 1)))
        next_attempt = now + int(delay)
        self.repo.patch_task(
            task.id,
            {
                "status": "queued",
                "retries": retries,
                "next_attempt_epoch": next_attempt,
                # Release claim to allow another worker to pick it up later.
                "claimed_by": "",
                "claimed_ts": "",
            },
        )
        _emit(
            conversation_id=task.conversation_id or "default",
            trace_id=task.trace_id or None,
            type="control_room.task.updated",
            severity="warning",
            payload={
                "task_id": task.id,
                "status": "queued",
                "retries": retries,
                "next_attempt_epoch": next_attempt,
            },
        )
