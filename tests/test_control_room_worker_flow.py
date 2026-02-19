from __future__ import annotations

import time
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_control_room_worker_safe_task_to_done(monkeypatch):
    monkeypatch.setenv("CONTROL_ROOM_ENABLED", "1")

    from denis_unified_v1.control_room.graph_repo import InMemoryControlRoomGraphRepo
    from denis_unified_v1.control_room.worker import ControlRoomWorker

    repo = InMemoryControlRoomGraphRepo()
    worker = ControlRoomWorker(repo=repo)

    tid = "task_safe_1"
    repo.create_task(
        task={
            "id": tid,
            "status": "queued",
            "type": "ops_query",
            "priority": "normal",
            "requester": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "payload_redacted_hash": "",
            "reason_safe": "safe",
            "created_ts": _utc_now_iso(),
            "retries": 0,
        }
    )
    r = worker.tick()
    assert r["errors"] == 0
    assert repo.get_task(tid).status == "done"


def test_control_room_worker_dangerous_task_waits_for_approval_then_runs(monkeypatch):
    monkeypatch.setenv("CONTROL_ROOM_ENABLED", "1")

    from denis_unified_v1.control_room.graph_repo import InMemoryControlRoomGraphRepo
    from denis_unified_v1.control_room.worker import ControlRoomWorker, _sha256  # type: ignore
    from denis_unified_v1.control_room.policies import get_policy_id
    from denis_unified_v1.control_room.approvals import resolve_approval

    repo = InMemoryControlRoomGraphRepo()
    worker = ControlRoomWorker(repo=repo)

    tid = "task_dang_1"
    repo.create_task(
        task={
            "id": tid,
            "status": "queued",
            "type": "deploy",
            "priority": "high",
            "requester": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "payload_redacted_hash": "",
            "reason_safe": "danger",
            "created_ts": _utc_now_iso(),
            "retries": 0,
        }
    )

    worker.tick()
    assert repo.get_task(tid).status == "waiting_approval"

    policy_id = get_policy_id("deploy")
    approval_id = _sha256(f"{tid}:{policy_id}:deploy")
    repo.approvals.setdefault(approval_id, {"id": approval_id, "scope": "deploy", "policy_id": policy_id, "requested_ts": _utc_now_iso()})
    repo.approvals[approval_id]["status"] = "approved"
    resolve_approval(
        approval_id=approval_id,
        action="approve",
        resolved_by="tester",
        reason_safe="ok",
        conversation_id="c1",
        trace_id="t1",
    )

    worker.tick()
    assert repo.get_task(tid).status == "done"


def test_control_room_worker_cancel(monkeypatch):
    monkeypatch.setenv("CONTROL_ROOM_ENABLED", "1")

    from denis_unified_v1.control_room.graph_repo import InMemoryControlRoomGraphRepo
    from denis_unified_v1.control_room.worker import ControlRoomWorker

    repo = InMemoryControlRoomGraphRepo()
    worker = ControlRoomWorker(repo=repo)

    tid = "task_cancel_1"
    repo.create_task(
        task={
            "id": tid,
            "status": "canceled",
            "type": "ops_query",
            "priority": "normal",
            "requester": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "payload_redacted_hash": "",
            "reason_safe": "cancel",
            "created_ts": _utc_now_iso(),
            "retries": 0,
        }
    )
    worker.tick()
    assert repo.get_task(tid).status == "canceled"


def test_control_room_worker_fail_closed_on_unverifiable_approval(monkeypatch):
    monkeypatch.setenv("CONTROL_ROOM_ENABLED", "1")

    from denis_unified_v1.control_room.graph_repo import GraphUnavailable, TaskRecord
    from denis_unified_v1.control_room.worker import ControlRoomWorker

    class Repo:
        def __init__(self) -> None:
            self.task = {
                "id": "task_fc_1",
                "status": "queued",
                "type": "deploy",
                "priority": "high",
                "requester": "test",
                "conversation_id": "c1",
                "trace_id": "t1",
                "payload_redacted_hash": "",
                "reason_safe": "danger",
                "created_ts": _utc_now_iso(),
                "updated_ts": "",
                "retries": 0,
            }

        def list_tasks_for_worker(self, *, now_epoch: int, limit: int = 10):
            return [TaskRecord.from_node(self.task)]

        def get_task(self, task_id: str):
            return TaskRecord.from_node(self.task)

        def patch_task(self, task_id: str, patch: dict):
            self.task.update(patch)

        def get_latest_approval_for_task(self, *, task_id: str, scope: str):
            raise GraphUnavailable("cannot_verify")

    repo = Repo()
    worker = ControlRoomWorker(repo=repo)
    worker.tick()
    # Must not execute dangerous task without verified approval.
    assert repo.task["status"] in {"waiting_approval", "queued", "failed"}

