"""Control Room graph repository.

Worker uses this as its only persistence interface. Default implementation reads/writes Neo4j
via `GraphClient` (fail-open). Tests can inject an in-memory repo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from denis_unified_v1.graph.graph_client import get_graph_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GraphUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskRecord:
    id: str
    status: str
    type: str
    priority: str
    requester: str
    conversation_id: str
    trace_id: str
    payload_redacted_hash: str
    reason_safe: str
    retries: int
    next_attempt_epoch: int | None
    created_ts: str
    updated_ts: str
    # WS11-G fields (all optional, safe primitives only).
    specialty: str = ""
    claimed_by: str = ""
    claimed_ts: str = ""
    no_overlap_contract_hash: str = ""
    requested_paths: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_node(cls, node: dict[str, Any]) -> "TaskRecord":
        rp = node.get("requested_paths")
        if isinstance(rp, (list, tuple)):
            requested_paths = tuple(str(x) for x in rp if isinstance(x, (str, int, float, bool)))
        else:
            requested_paths = tuple()
        return cls(
            id=str(node.get("id") or ""),
            status=str(node.get("status") or ""),
            type=str(node.get("type") or node.get("task_type") or ""),
            priority=str(node.get("priority") or "normal"),
            requester=str(node.get("requester") or ""),
            conversation_id=str(node.get("conversation_id") or "default"),
            trace_id=str(node.get("trace_id") or ""),
            payload_redacted_hash=str(node.get("payload_redacted_hash") or ""),
            reason_safe=str(node.get("reason_safe") or ""),
            retries=int(node.get("retries") or 0),
            next_attempt_epoch=int(node.get("next_attempt_epoch")) if node.get("next_attempt_epoch") is not None else None,
            created_ts=str(node.get("created_ts") or ""),
            updated_ts=str(node.get("updated_ts") or ""),
            specialty=str(node.get("specialty") or ""),
            claimed_by=str(node.get("claimed_by") or ""),
            claimed_ts=str(node.get("claimed_ts") or ""),
            no_overlap_contract_hash=str(node.get("no_overlap_contract_hash") or ""),
            requested_paths=requested_paths,
        )


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    status: str
    policy_id: str
    scope: str
    requested_ts: str
    resolved_ts: str

    @classmethod
    def from_node(cls, node: dict[str, Any]) -> "ApprovalRecord":
        return cls(
            id=str(node.get("id") or ""),
            status=str(node.get("status") or ""),
            policy_id=str(node.get("policy_id") or ""),
            scope=str(node.get("scope") or ""),
            requested_ts=str(node.get("requested_ts") or ""),
            resolved_ts=str(node.get("resolved_ts") or ""),
        )


class ControlRoomGraphRepo:
    """Neo4j-backed repo (best-effort)."""

    def _driver(self):
        gc = get_graph_client()
        driver = gc._get_driver()
        if driver is None:
            raise GraphUnavailable("neo4j_unavailable")
        return driver

    def list_tasks_for_worker(self, *, now_epoch: int, limit: int = 10, specialty: str | None = None) -> list[TaskRecord]:
        driver = self._driver()
        lim = max(1, min(int(limit), 50))
        now_epoch_i = int(now_epoch)
        specialty_s = (specialty or "").strip()

        cypher = """
        MATCH (t:Task)
        WHERE t.status IN ['queued', 'waiting_approval']
          AND (t.status <> 'queued' OR (t.claimed_by IS NULL OR t.claimed_by = ''))
          AND (t.next_attempt_epoch IS NULL OR t.next_attempt_epoch <= $now_epoch)
          AND ($specialty = '' OR t.specialty = $specialty)
        WITH t,
          CASE COALESCE(t.priority, 'normal')
            WHEN 'critical' THEN 4
            WHEN 'high' THEN 3
            WHEN 'normal' THEN 2
            WHEN 'low' THEN 1
            ELSE 2
          END AS pr
        RETURN t
        ORDER BY pr DESC, t.created_ts ASC
        LIMIT $limit
        """
        out: list[TaskRecord] = []
        with driver.session() as session:
            res = session.run(cypher, now_epoch=now_epoch_i, limit=lim, specialty=specialty_s)
            for rec in res:
                try:
                    out.append(TaskRecord.from_node(dict(rec["t"])))
                except Exception:
                    continue
        return out

    def get_task(self, task_id: str) -> TaskRecord | None:
        driver = self._driver()
        with driver.session() as session:
            res = session.run("MATCH (t:Task {id: $id}) RETURN t", id=str(task_id))
            rec = res.single()
            if not rec:
                return None
            return TaskRecord.from_node(dict(rec["t"]))

    def patch_task(self, task_id: str, patch: dict[str, Any]) -> None:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        p = dict(patch or {})
        p.setdefault("updated_ts", _utc_now_iso())
        gc.upsert_task(task_id=str(task_id), props=p)

    def try_claim_task(self, *, task_id: str, worker_id: str) -> bool:
        """Graph-centric lock/claim.

        Atomic condition: status=queued AND claimed_by is null/empty.
        Returns True iff the claim was applied.
        """
        driver = self._driver()
        wid = (worker_id or "").strip()
        if not wid:
            return False
        ts = _utc_now_iso()
        cypher = """
        MATCH (t:Task {id: $id})
        WHERE t.status = 'queued' AND (t.claimed_by IS NULL OR t.claimed_by = '')
        SET t.claimed_by = $wid,
            t.claimed_ts = $ts,
            t.updated_ts = $ts
        RETURN t.id AS id
        """
        with driver.session() as session:
            res = session.run(cypher, id=str(task_id), wid=wid, ts=ts)
            rec = res.single()
            return bool(rec and rec.get("id"))

    def get_latest_approval_for_task(self, *, task_id: str, scope: str) -> ApprovalRecord | None:
        driver = self._driver()
        cypher = """
        MATCH (t:Task {id: $task_id})-[:REQUIRES_APPROVAL]->(a:Approval)
        WHERE a.scope = $scope
        RETURN a
        ORDER BY a.requested_ts DESC
        LIMIT 1
        """
        with driver.session() as session:
            res = session.run(cypher, task_id=str(task_id), scope=str(scope))
            rec = res.single()
            if not rec:
                return None
            return ApprovalRecord.from_node(dict(rec["a"]))


class InMemoryControlRoomGraphRepo:
    """In-memory repo for unit tests and smoke scripts."""

    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.task_to_approvals: dict[str, list[str]] = {}

    def create_task(self, *, task: dict[str, Any]) -> None:
        tid = str(task.get("id") or "")
        self.tasks[tid] = dict(task)

    def list_tasks_for_worker(self, *, now_epoch: int, limit: int = 10, specialty: str | None = None) -> list[TaskRecord]:
        now_epoch_i = int(now_epoch)
        specialty_s = (specialty or "").strip()
        items = []
        for t in self.tasks.values():
            st = str(t.get("status") or "")
            if st not in {"queued", "waiting_approval"}:
                continue
            if specialty_s and str(t.get("specialty") or "") != specialty_s:
                continue
            if st == "queued" and str(t.get("claimed_by") or ""):
                continue
            nxt = t.get("next_attempt_epoch")
            if nxt is not None and int(nxt) > now_epoch_i:
                continue
            items.append(t)

        pr_rank = {"critical": 4, "high": 3, "normal": 2, "low": 1}
        items.sort(key=lambda x: (-pr_rank.get(str(x.get("priority") or "normal"), 2), str(x.get("created_ts") or "")))
        out: list[TaskRecord] = []
        for t in items[: max(1, min(int(limit), 50))]:
            out.append(TaskRecord.from_node(t))
        return out

    def get_task(self, task_id: str) -> TaskRecord | None:
        t = self.tasks.get(str(task_id))
        if not t:
            return None
        return TaskRecord.from_node(t)

    def patch_task(self, task_id: str, patch: dict[str, Any]) -> None:
        tid = str(task_id)
        if tid not in self.tasks:
            self.tasks[tid] = {"id": tid}
        self.tasks[tid].update(dict(patch or {}))
        self.tasks[tid].setdefault("updated_ts", _utc_now_iso())

    def try_claim_task(self, *, task_id: str, worker_id: str) -> bool:
        wid = (worker_id or "").strip()
        if not wid:
            return False
        t = self.tasks.get(str(task_id)) or {}
        if str(t.get("status") or "") != "queued":
            return False
        if str(t.get("claimed_by") or ""):
            return False
        ts = _utc_now_iso()
        t["claimed_by"] = wid
        t["claimed_ts"] = ts
        t["updated_ts"] = ts
        self.tasks[str(task_id)] = t
        return True

    def put_approval(self, *, approval: dict[str, Any], task_id: str) -> None:
        aid = str(approval.get("id") or approval.get("approval_id") or "")
        self.approvals[aid] = dict(approval)
        self.task_to_approvals.setdefault(str(task_id), []).append(aid)

    def get_latest_approval_for_task(self, *, task_id: str, scope: str) -> ApprovalRecord | None:
        aids = self.task_to_approvals.get(str(task_id)) or []
        candidates = []
        for aid in aids:
            a = self.approvals.get(aid)
            if not a:
                continue
            if str(a.get("scope") or "") != str(scope):
                continue
            candidates.append(a)
        candidates.sort(key=lambda x: str(x.get("requested_ts") or ""), reverse=True)
        if not candidates:
            return None
        return ApprovalRecord.from_node(candidates[0])
