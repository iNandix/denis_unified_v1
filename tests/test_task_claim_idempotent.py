from __future__ import annotations

from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_task_claim_idempotent_inmemory(monkeypatch):
    monkeypatch.setenv("CONTROL_ROOM_ENABLED", "1")

    from denis_unified_v1.control_room.graph_repo import InMemoryControlRoomGraphRepo
    from denis_unified_v1.control_room.specialties import get_specialty

    repo = InMemoryControlRoomGraphRepo()
    spec = get_specialty("s1_core")

    tid = "task_claim_1"
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
            "specialty": "s1_core",
            "no_overlap_contract_hash": spec.no_overlap_contract_hash,
            "requested_paths": ["denis_unified_v1/control_room/worker.py"],
        }
    )

    ok1 = repo.try_claim_task(task_id=tid, worker_id="w1")
    ok2 = repo.try_claim_task(task_id=tid, worker_id="w2")
    assert ok1 is True
    assert ok2 is False

    t = repo.get_task(tid)
    assert t is not None
    assert t.claimed_by == "w1"
    assert t.claimed_ts

