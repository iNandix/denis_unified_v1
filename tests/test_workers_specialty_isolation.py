from __future__ import annotations

from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_workers_claim_by_specialty_and_isolation(monkeypatch):
    monkeypatch.setenv("CONTROL_ROOM_ENABLED", "1")

    from denis_unified_v1.control_room.graph_repo import InMemoryControlRoomGraphRepo
    from denis_unified_v1.control_room.specialties import get_specialty
    from denis_unified_v1.control_room.worker import ControlRoomWorker

    repo = InMemoryControlRoomGraphRepo()

    specs = {sid: get_specialty(sid) for sid in ["s1_core", "s2_voice", "s3_front", "s4_govops"]}
    paths = {
        "s1_core": "denis_unified_v1/control_room/worker.py",
        "s2_voice": "voice/__init__.py",
        "s3_front": "static/async_status.html",
        "s4_govops": "docs/graph/ssot_contract.md",
    }

    for sid in ["s1_core", "s2_voice", "s3_front", "s4_govops"]:
        repo.create_task(
            task={
                "id": f"task_{sid}",
                "status": "queued",
                "type": "ops_query",
                "priority": "normal",
                "requester": "test",
                "conversation_id": "c1",
                "trace_id": f"t_{sid}",
                "payload_redacted_hash": "",
                "reason_safe": "safe",
                "created_ts": _utc_now_iso(),
                "retries": 0,
                "specialty": sid,
                "no_overlap_contract_hash": specs[sid].no_overlap_contract_hash,
                "requested_paths": [paths[sid]],
            }
        )

    workers = {
        "s1_core": ControlRoomWorker(repo=repo, worker_id="w_core", specialty="s1_core"),
        "s2_voice": ControlRoomWorker(repo=repo, worker_id="w_voice", specialty="s2_voice"),
        "s3_front": ControlRoomWorker(repo=repo, worker_id="w_front", specialty="s3_front"),
        "s4_govops": ControlRoomWorker(repo=repo, worker_id="w_gov", specialty="s4_govops"),
    }

    for w in workers.values():
        r = w.tick()
        assert r["errors"] == 0

    assert repo.get_task("task_s1_core").status == "done"
    assert repo.get_task("task_s1_core").claimed_by == "w_core"
    assert repo.get_task("task_s2_voice").status == "done"
    assert repo.get_task("task_s2_voice").claimed_by == "w_voice"
    assert repo.get_task("task_s3_front").status == "done"
    assert repo.get_task("task_s3_front").claimed_by == "w_front"
    assert repo.get_task("task_s4_govops").status == "done"
    assert repo.get_task("task_s4_govops").claimed_by == "w_gov"


def test_worker_refuses_outside_ownership(monkeypatch):
    monkeypatch.setenv("CONTROL_ROOM_ENABLED", "1")

    from denis_unified_v1.control_room.graph_repo import InMemoryControlRoomGraphRepo
    from denis_unified_v1.control_room.specialties import get_specialty
    from denis_unified_v1.control_room.worker import ControlRoomWorker

    repo = InMemoryControlRoomGraphRepo()
    spec = get_specialty("s1_core")

    tid = "task_violate"
    repo.create_task(
        task={
            "id": tid,
            "status": "queued",
            "type": "ops_query",
            "priority": "normal",
            "requester": "test",
            "conversation_id": "c1",
            "trace_id": "t_violate",
            "payload_redacted_hash": "",
            "reason_safe": "safe",
            "created_ts": _utc_now_iso(),
            "retries": 0,
            "specialty": "s1_core",
            "no_overlap_contract_hash": spec.no_overlap_contract_hash,
            "requested_paths": ["static/async_status.html"],
        }
    )

    worker = ControlRoomWorker(repo=repo, worker_id="w_core", specialty="s1_core")
    r = worker.tick()
    assert r["errors"] == 0
    t = repo.get_task(tid)
    assert t.status == "failed"
    assert t.claimed_by == ""

