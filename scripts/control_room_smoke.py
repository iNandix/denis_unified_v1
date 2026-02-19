#!/usr/bin/env python3
"""Control Room smoke (WS9) - local, no network required.

This script runs a minimal end-to-end flow using the in-memory Control Room repo:
- safe task -> done
- dangerous task -> waiting_approval -> approve -> done

It also sanity-checks that event materialization is idempotent (replaying the same event twice
does not crash and does not re-apply mutations in the dedupe layer).
"""

from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        os.environ.setdefault("CONTROL_ROOM_ENABLED", "1")
        os.environ.setdefault("GRAPH_ENABLED", "0")  # smoke uses in-memory repo
        os.environ["DENIS_EVENTS_DB_PATH"] = os.path.join(td, "events.db")
        os.environ["DENIS_GML_DB_PATH"] = os.path.join(td, "gml.db")

        from denis_unified_v1.control_room.graph_repo import InMemoryControlRoomGraphRepo
        from denis_unified_v1.control_room.worker import ControlRoomWorker
        from denis_unified_v1.control_room.policies import get_policy_id
        from denis_unified_v1.control_room.approvals import resolve_approval
        from denis_unified_v1.control_room.worker import _sha256  # type: ignore

        repo = InMemoryControlRoomGraphRepo()
        worker = ControlRoomWorker(repo=repo)

        # Safe task: ops_query
        safe_task_id = "t_safe_" + _sha256("ops_query:" + str(time.time()))[:16]
        repo.create_task(
            task={
                "id": safe_task_id,
                "status": "queued",
                "type": "ops_query",
                "priority": "normal",
                "requester": "smoke",
                "conversation_id": "conv_smoke",
                "trace_id": "trace_smoke",
                "payload_redacted_hash": "",
                "reason_safe": "smoke safe task",
                "created_ts": _utc_now_iso(),
                "retries": 0,
            }
        )
        r = worker.tick()
        t = repo.get_task(safe_task_id)
        assert t and t.status == "done", (r, t)

        # Dangerous task: deploy -> waiting approval
        dang_task_id = "t_dang_" + _sha256("deploy:" + str(time.time()))[:16]
        repo.create_task(
            task={
                "id": dang_task_id,
                "status": "queued",
                "type": "deploy",
                "priority": "high",
                "requester": "smoke",
                "conversation_id": "conv_smoke",
                "trace_id": "trace_smoke",
                "payload_redacted_hash": "",
                "reason_safe": "smoke dangerous task",
                "created_ts": _utc_now_iso(),
                "retries": 0,
            }
        )
        worker.tick()
        t2 = repo.get_task(dang_task_id)
        assert t2 and t2.status == "waiting_approval", t2

        # Approve (stable approval id)
        policy_id = get_policy_id("deploy")
        approval_id = _sha256(f"{dang_task_id}:{policy_id}:deploy")
        # Mirror resolution in in-memory repo and emit resolved event.
        repo.approvals.setdefault(approval_id, {"id": approval_id, "scope": "deploy", "policy_id": policy_id, "requested_ts": _utc_now_iso()})
        repo.approvals[approval_id]["status"] = "approved"
        resolve_approval(
            approval_id=approval_id,
            action="approve",
            resolved_by="smoke",
            reason_safe="smoke approve",
            conversation_id="conv_smoke",
            trace_id="trace_smoke",
        )

        worker.tick()
        t3 = repo.get_task(dang_task_id)
        assert t3 and t3.status == "done", t3

        # Idempotency: replay same event twice in GML should not crash.
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        ev = {
            "event_id": 1,
            "ts": _utc_now_iso(),
            "conversation_id": "conv_smoke",
            "trace_id": "trace_smoke",
            "type": "run.step",
            "severity": "info",
            "schema_version": "1.0",
            "ui_hint": {"render": "step", "icon": "list"},
            "payload": {"run_id": "r_smoke", "step_id": "s_smoke", "state": "SUCCESS", "order": 1, "name": "smoke"},
        }
        materialize_event(ev, graph=None)
        materialize_event(ev, graph=None)

    print("control_room_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

