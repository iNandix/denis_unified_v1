"""Tests for Control Room Graph Materialization Layer (GML).

Covers:
- control_room.task.created -> Task node with correct props
- control_room.task.updated -> Task status patch
- control_room.run.spawned -> Run + SPAWNS edge
- control_room.approval.requested -> Approval + edges
- control_room.approval.resolved -> Approval patch
- control_room.action.updated -> Action + edges
- Idempotency (same event twice => no duplicates)
- Fail-open (graph disabled => no crash)
- No raw payload in graph (all node props are short/safe)
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_event(
    *,
    event_id: int = 1,
    etype: str = "control_room.task.created",
    conversation_id: str = "conv_cr_test",
    trace_id: str = "trace_cr_test",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "ts": _utc_now_iso(),
        "conversation_id": conversation_id,
        "trace_id": trace_id,
        "type": etype,
        "severity": "info",
        "schema_version": "1.0",
        "ui_hint": {"render": "event"},
        "payload": payload or {},
    }


@pytest.fixture(autouse=True)
def _clean_gml_env(tmp_path, monkeypatch):
    """Ensure isolated GML DB + graph enabled with mock driver for unit tests."""
    db_path = str(tmp_path / "test_cr_gml.db")
    monkeypatch.setenv("DENIS_GML_DB_PATH", db_path)
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("NEO4J_PASSWORD", "test_pass")
    yield


class FakeGraphClient:
    """In-memory graph client for testing Control Room mutations."""

    def __init__(self) -> None:
        self.enabled = True
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self._last_ok_ts = ""
        self._last_err_ts = ""
        self._errors_window = 0

    def status(self):
        from denis_unified_v1.graph.graph_client import GraphStatus

        return GraphStatus(
            enabled=True,
            up=True,
            last_ok_ts=self._last_ok_ts,
            last_err_ts=self._last_err_ts,
            errors_window=self._errors_window,
        )

    def run_write(self, cypher: str, params: dict[str, Any] | None = None) -> bool:
        self._last_ok_ts = _utc_now_iso()
        return True

    # --- Existing node upserts ---
    def upsert_component(self, *, component_id: str, props: dict[str, Any]) -> bool:
        self.nodes[f"Component:{component_id}"] = {"id": component_id, **props}
        return True

    def upsert_provider(self, *, provider_id: str, kind: str | None = None) -> bool:
        self.nodes[f"Provider:{provider_id}"] = {"id": provider_id, "kind": kind}
        return True

    def upsert_feature_flag(self, *, flag_id: str, value: str) -> bool:
        self.nodes[f"FeatureFlag:{flag_id}"] = {"id": flag_id, "value": value}
        return True

    def upsert_run(self, *, run_id: str, props: dict[str, Any]) -> bool:
        self.nodes[f"Run:{run_id}"] = {"id": run_id, **props}
        return True

    def upsert_step(self, *, step_id: str, props: dict[str, Any]) -> bool:
        self.nodes[f"Step:{step_id}"] = {"id": step_id, **props}
        return True

    def upsert_artifact(self, *, artifact_id: str, props: dict[str, Any]) -> bool:
        self.nodes[f"Artifact:{artifact_id}"] = {"id": artifact_id, **props}
        return True

    def upsert_source(self, *, source_id: str, props: dict[str, Any]) -> bool:
        self.nodes[f"Source:{source_id}"] = {"id": source_id, **props}
        return True

    # --- Control Room node upserts ---
    def upsert_task(self, *, task_id: str, props: dict[str, Any]) -> bool:
        self.nodes[f"Task:{task_id}"] = {"id": task_id, **props}
        return True

    def upsert_approval(self, *, approval_id: str, props: dict[str, Any]) -> bool:
        self.nodes[f"Approval:{approval_id}"] = {"id": approval_id, **props}
        return True

    def upsert_action(self, *, action_id: str, props: dict[str, Any]) -> bool:
        self.nodes[f"Action:{action_id}"] = {"id": action_id, **props}
        return True

    # --- Existing edge links ---
    def link_run_step(self, *, run_id: str, step_id: str, order: int) -> bool:
        self.edges.append({"type": "HAS_STEP", "from": run_id, "to": step_id, "order": order})
        return True

    def link_step_artifact(self, *, step_id: str, artifact_id: str) -> bool:
        self.edges.append({"type": "PRODUCED", "from": step_id, "to": artifact_id})
        return True

    def link_artifact_source(self, *, artifact_id: str, source_id: str) -> bool:
        self.edges.append({"type": "FROM_SOURCE", "from": artifact_id, "to": source_id})
        return True

    def link_run_provider(self, *, run_id: str, provider_id: str, role: str) -> bool:
        self.edges.append({"type": "USED_PROVIDER", "from": run_id, "to": provider_id, "role": role})
        return True

    def link_component_flag(self, *, component_id: str, flag_id: str) -> bool:
        self.edges.append({"type": "GATED_BY", "from": component_id, "to": flag_id})
        return True

    def link_component_depends_on(self, *, component_id: str, depends_on_id: str) -> bool:
        self.edges.append({"type": "DEPENDS_ON", "from": component_id, "to": depends_on_id})
        return True

    # --- Control Room edge links ---
    def link_task_run(self, *, task_id: str, run_id: str) -> bool:
        self.edges.append({"type": "SPAWNS", "from": task_id, "to": run_id})
        return True

    def link_task_approval(self, *, task_id: str, approval_id: str) -> bool:
        self.edges.append({"type": "REQUIRES_APPROVAL", "from": task_id, "to": approval_id})
        return True

    def link_approval_run(self, *, approval_id: str, run_id: str) -> bool:
        self.edges.append({"type": "GOVERNS", "from": approval_id, "to": run_id})
        return True

    def link_approval_step(self, *, approval_id: str, step_id: str) -> bool:
        self.edges.append({"type": "GOVERNS", "from": approval_id, "to": step_id})
        return True

    def link_step_action(self, *, step_id: str, action_id: str, order: int) -> bool:
        self.edges.append({"type": "HAS_ACTION", "from": step_id, "to": action_id, "order": order})
        return True

    def link_step_component(self, *, step_id: str, component_id: str) -> bool:
        self.edges.append({"type": "TOUCHED", "from": step_id, "to": component_id})
        return True


# ─── control_room.task.created ───


class TestTaskCreatedMapping:
    def test_creates_task_node_with_correct_props(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.task.created",
            payload={
                "task_id": "task_001",
                "type": "run_pipeline",
                "priority": "high",
                "requester": "user:alice",
                "payload_redacted_hash": "abc123hash",
                "reason_safe": "Deploy new model",
            },
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "control_room"
        assert "cr_task_created" in result.mutation_kinds

        # Task node should exist with correct props
        assert "Task:task_001" in g.nodes
        task = g.nodes["Task:task_001"]
        assert task["status"] == "queued"
        assert task["type"] == "run_pipeline"
        assert task["priority"] == "high"
        assert task["requester"] == "user:alice"
        assert task["payload_redacted_hash"] == "abc123hash"
        assert task["reason_safe"] == "Deploy new model"

        # Component freshness should be updated
        assert "Component:control_room" in g.nodes

    def test_missing_task_id_returns_not_handled(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.task.created",
            payload={"type": "run_pipeline"},  # no task_id
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is False
        # No Task node should be created
        task_nodes = [k for k in g.nodes if k.startswith("Task:")]
        assert len(task_nodes) == 0


# ─── control_room.task.updated ───


class TestTaskUpdatedMapping:
    def test_patches_task_status(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        # First create the task
        ev_create = _make_event(
            event_id=1,
            etype="control_room.task.created",
            payload={"task_id": "task_002", "type": "execute_action", "priority": "normal", "requester": "system"},
        )
        materialize_event(ev_create, graph=g)

        # Now update it
        ev_update = _make_event(
            event_id=2,
            etype="control_room.task.updated",
            payload={
                "task_id": "task_002",
                "status": "running",
                "started_ts": "2025-01-15T10:00:00Z",
            },
        )
        result = materialize_event(ev_update, graph=g)

        assert result.handled is True
        assert result.component_id == "control_room"
        assert "cr_task_updated" in result.mutation_kinds

        task = g.nodes["Task:task_002"]
        assert task["status"] == "running"
        assert task["started_ts"] == "2025-01-15T10:00:00Z"

    def test_patches_task_with_retries(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.task.updated",
            payload={"task_id": "task_003", "status": "failed", "retries": 3, "ended_ts": "2025-01-15T12:00:00Z"},
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        task = g.nodes["Task:task_003"]
        assert task["retries"] == 3
        assert task["status"] == "failed"

    def test_missing_task_id_returns_not_handled(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.task.updated",
            payload={"status": "running"},
        )
        result = materialize_event(ev, graph=g)
        assert result.handled is False


# ─── control_room.run.spawned ───


class TestRunSpawnedMapping:
    def test_creates_run_and_spawns_edge(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.run.spawned",
            payload={"task_id": "task_010", "run_id": "run_010"},
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "control_room"
        assert "cr_run_spawned" in result.mutation_kinds

        # Run node should exist with kind=control_room
        assert "Run:run_010" in g.nodes
        run_node = g.nodes["Run:run_010"]
        assert run_node["kind"] == "control_room"
        assert run_node["status"] == "running"

        # SPAWNS edge should exist
        spawns_edges = [e for e in g.edges if e["type"] == "SPAWNS"]
        assert len(spawns_edges) >= 1
        assert any(e["from"] == "task_010" and e["to"] == "run_010" for e in spawns_edges)

        # Component freshness
        assert "Component:control_room" in g.nodes

    def test_missing_task_id_returns_not_handled(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.run.spawned",
            payload={"run_id": "run_011"},  # no task_id
        )
        result = materialize_event(ev, graph=g)
        assert result.handled is False

    def test_missing_run_id_returns_not_handled(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.run.spawned",
            payload={"task_id": "task_012"},  # no run_id
        )
        result = materialize_event(ev, graph=g)
        assert result.handled is False


# ─── control_room.approval.requested ───


class TestApprovalRequestedMapping:
    def test_creates_approval_with_edges(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.approval.requested",
            payload={
                "approval_id": "appr_001",
                "task_id": "task_020",
                "policy_id": "policy_destructive",
                "scope": "destructive_write",
                "run_id": "run_020",
            },
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "control_room"
        assert "cr_approval_requested" in result.mutation_kinds

        # Approval node
        assert "Approval:appr_001" in g.nodes
        appr = g.nodes["Approval:appr_001"]
        assert appr["status"] == "pending"
        assert appr["policy_id"] == "policy_destructive"
        assert appr["scope"] == "destructive_write"

        # REQUIRES_APPROVAL edge from task
        req_edges = [e for e in g.edges if e["type"] == "REQUIRES_APPROVAL"]
        assert any(e["from"] == "task_020" and e["to"] == "appr_001" for e in req_edges)

        # GOVERNS edge to run
        gov_edges = [e for e in g.edges if e["type"] == "GOVERNS"]
        assert any(e["from"] == "appr_001" and e["to"] == "run_020" for e in gov_edges)

    def test_approval_governs_step(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.approval.requested",
            payload={
                "approval_id": "appr_002",
                "task_id": "task_021",
                "policy_id": "policy_step_gate",
                "scope": "external_call",
                "step_id": "step_021",
            },
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        gov_edges = [e for e in g.edges if e["type"] == "GOVERNS"]
        assert any(e["from"] == "appr_002" and e["to"] == "step_021" for e in gov_edges)

    def test_missing_approval_id_returns_not_handled(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.approval.requested",
            payload={"task_id": "task_022", "policy_id": "p1", "scope": "s1"},
        )
        result = materialize_event(ev, graph=g)
        assert result.handled is False


# ─── control_room.approval.resolved ───


class TestApprovalResolvedMapping:
    def test_patches_approval_status(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        # First request the approval
        ev_req = _make_event(
            event_id=1,
            etype="control_room.approval.requested",
            payload={
                "approval_id": "appr_010",
                "task_id": "task_030",
                "policy_id": "p1",
                "scope": "destructive_write",
                "run_id": "run_030",
            },
        )
        materialize_event(ev_req, graph=g)

        # Then resolve it
        ev_resolve = _make_event(
            event_id=2,
            etype="control_room.approval.resolved",
            payload={
                "approval_id": "appr_010",
                "status": "approved",
                "resolved_by": "user:bob",
                "resolved_ts": "2025-01-15T14:00:00Z",
                "reason_safe": "Approved by team lead",
            },
        )
        result = materialize_event(ev_resolve, graph=g)

        assert result.handled is True
        assert result.component_id == "control_room"
        assert "cr_approval_resolved" in result.mutation_kinds

        appr = g.nodes["Approval:appr_010"]
        assert appr["status"] == "approved"
        assert appr["resolved_by"] == "user:bob"
        assert appr["resolved_ts"] == "2025-01-15T14:00:00Z"
        assert appr["reason_safe"] == "Approved by team lead"

    def test_denied_approval(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.approval.resolved",
            payload={
                "approval_id": "appr_011",
                "status": "denied",
                "resolved_by": "policy:auto_deny",
                "resolved_ts": "2025-01-15T15:00:00Z",
                "reason_safe": "Policy violation",
            },
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        appr = g.nodes["Approval:appr_011"]
        assert appr["status"] == "denied"

    def test_missing_approval_id_returns_not_handled(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.approval.resolved",
            payload={"status": "approved", "resolved_by": "user:bob"},
        )
        result = materialize_event(ev, graph=g)
        assert result.handled is False


# ─── control_room.action.updated ───


class TestActionUpdatedMapping:
    def test_creates_action_with_step_edge(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.action.updated",
            payload={
                "action_id": "act_001",
                "step_id": "step_040",
                "name": "deploy_model",
                "tool": "kubectl_apply",
                "status": "running",
                "order": 2,
                "args_redacted_hash": "hash_args_001",
                "result_redacted_hash": "hash_result_001",
            },
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "control_room"
        assert "cr_action_updated" in result.mutation_kinds

        # Action node
        assert "Action:act_001" in g.nodes
        act = g.nodes["Action:act_001"]
        assert act["name"] == "deploy_model"
        assert act["tool"] == "kubectl_apply"
        assert act["status"] == "running"
        assert act["args_redacted_hash"] == "hash_args_001"
        assert act["result_redacted_hash"] == "hash_result_001"

        # HAS_ACTION edge
        ha_edges = [e for e in g.edges if e["type"] == "HAS_ACTION"]
        assert any(e["from"] == "step_040" and e["to"] == "act_001" and e["order"] == 2 for e in ha_edges)

    def test_action_without_step_id(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.action.updated",
            payload={
                "action_id": "act_002",
                "name": "standalone_action",
                "tool": "custom_tool",
                "status": "success",
                "args_redacted_hash": "hash_args_002",
                "result_redacted_hash": "hash_result_002",
            },
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert "Action:act_002" in g.nodes
        # No HAS_ACTION edge should be created (no step_id)
        ha_edges = [e for e in g.edges if e["type"] == "HAS_ACTION"]
        assert not any(e["to"] == "act_002" for e in ha_edges)

    def test_missing_action_id_returns_not_handled(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.action.updated",
            payload={"name": "orphan", "tool": "t"},
        )
        result = materialize_event(ev, graph=g)
        assert result.handled is False


# ─── Idempotency ───


class TestControlRoomIdempotency:
    def test_same_task_created_event_twice_no_duplicate(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            event_id=100,
            etype="control_room.task.created",
            payload={"task_id": "task_idem_1", "type": "pipeline", "priority": "high", "requester": "system"},
        )

        r1 = materialize_event(ev, graph=g)
        nodes_after_first = dict(g.nodes)
        edges_after_first = list(g.edges)

        r2 = materialize_event(ev, graph=g)

        assert r1.handled is True
        assert r2.handled is True

        # Task node should still be exactly one
        task_nodes = [k for k in g.nodes if k.startswith("Task:task_idem_1")]
        assert len(task_nodes) == 1

    def test_same_approval_event_twice_no_duplicate_edges(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            event_id=200,
            etype="control_room.approval.requested",
            payload={
                "approval_id": "appr_idem_1",
                "task_id": "task_idem_2",
                "policy_id": "p1",
                "scope": "write",
                "run_id": "run_idem_1",
            },
        )

        materialize_event(ev, graph=g)
        edges_after_first = len(g.edges)

        materialize_event(ev, graph=g)
        edges_after_second = len(g.edges)

        # Second call should not add edges (SQLite dedupe prevents re-execution)
        assert edges_after_second == edges_after_first

    def test_same_action_event_twice_no_duplicate(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            event_id=300,
            etype="control_room.action.updated",
            payload={
                "action_id": "act_idem_1",
                "step_id": "step_idem_1",
                "name": "deploy",
                "tool": "kubectl",
                "status": "running",
                "order": 1,
                "args_redacted_hash": "h1",
                "result_redacted_hash": "h2",
            },
        )

        materialize_event(ev, graph=g)
        edges_first = len(g.edges)

        materialize_event(ev, graph=g)
        edges_second = len(g.edges)

        assert edges_second == edges_first


# ─── Fail-open ───


class TestControlRoomFailOpen:
    def test_graph_disabled_returns_not_handled(self, monkeypatch):
        monkeypatch.setenv("GRAPH_ENABLED", "0")
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event
        from denis_unified_v1.graph.graph_client import GraphClient

        g = GraphClient()  # Will be disabled
        ev = _make_event(
            etype="control_room.task.created",
            payload={"task_id": "task_fail_1", "type": "pipeline", "priority": "normal", "requester": "system"},
        )
        result = materialize_event(ev, graph=g)
        assert result.handled is False

    def test_graph_error_on_upsert_task_swallowed(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        g.upsert_task = MagicMock(side_effect=RuntimeError("db_down"))
        g.upsert_run = MagicMock(side_effect=RuntimeError("db_down"))
        g.upsert_component = MagicMock(side_effect=RuntimeError("db_down"))

        ev = _make_event(
            etype="control_room.task.created",
            payload={"task_id": "task_fail_2", "type": "pipeline", "priority": "normal", "requester": "system"},
        )
        # Should NOT raise
        result = materialize_event(ev, graph=g)
        assert result.handled is False

    def test_graph_error_on_approval_swallowed(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        g.upsert_approval = MagicMock(side_effect=RuntimeError("db_down"))
        g.upsert_run = MagicMock(side_effect=RuntimeError("db_down"))
        g.upsert_component = MagicMock(side_effect=RuntimeError("db_down"))

        ev = _make_event(
            etype="control_room.approval.requested",
            payload={"approval_id": "appr_fail_1", "task_id": "t1", "policy_id": "p1", "scope": "s1"},
        )
        # Should NOT raise
        result = materialize_event(ev, graph=g)
        assert result.handled is False

    def test_maybe_materialize_never_raises_on_cr_events(self):
        from denis_unified_v1.graph.materializers.event_materializer import maybe_materialize_event

        g = FakeGraphClient()
        g.upsert_task = MagicMock(side_effect=RuntimeError("catastrophic"))
        g.upsert_run = MagicMock(side_effect=RuntimeError("catastrophic"))
        g.upsert_component = MagicMock(side_effect=RuntimeError("catastrophic"))

        ev = _make_event(
            etype="control_room.task.created",
            payload={"task_id": "task_fail_3", "type": "pipeline", "priority": "normal", "requester": "system"},
        )
        # Must NOT raise
        maybe_materialize_event(ev, graph=g)


# ─── No raw payload in graph ───


class TestNoRawPayloadInGraph:
    def test_task_created_no_long_strings(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.task.created",
            payload={
                "task_id": "task_safe_1",
                "type": "run_pipeline",
                "priority": "high",
                "requester": "user:alice",
                "payload_redacted_hash": "a" * 64,
                "reason_safe": "Short safe reason",
            },
        )
        materialize_event(ev, graph=g)

        for key, node in g.nodes.items():
            for field, value in node.items():
                if isinstance(value, str) and len(value) > 500:
                    pytest.fail(f"Graph node {key}.{field} contains long text ({len(value)} chars)")

    def test_approval_no_long_strings(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.approval.requested",
            payload={
                "approval_id": "appr_safe_1",
                "task_id": "task_safe_2",
                "policy_id": "policy_safe",
                "scope": "destructive_write",
                "run_id": "run_safe_1",
            },
        )
        materialize_event(ev, graph=g)

        for key, node in g.nodes.items():
            for field, value in node.items():
                if isinstance(value, str) and len(value) > 500:
                    pytest.fail(f"Graph node {key}.{field} contains long text ({len(value)} chars)")

    def test_action_no_long_strings(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="control_room.action.updated",
            payload={
                "action_id": "act_safe_1",
                "step_id": "step_safe_1",
                "name": "deploy_model",
                "tool": "kubectl_apply",
                "status": "success",
                "order": 1,
                "args_redacted_hash": "b" * 64,
                "result_redacted_hash": "c" * 64,
            },
        )
        materialize_event(ev, graph=g)

        for key, node in g.nodes.items():
            for field, value in node.items():
                if isinstance(value, str) and len(value) > 500:
                    pytest.fail(f"Graph node {key}.{field} contains long text ({len(value)} chars)")

    def test_all_cr_events_produce_safe_props(self):
        """End-to-end: emit all 6 CR event types and verify no raw content leaks."""
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        events = [
            _make_event(event_id=1, etype="control_room.task.created", payload={
                "task_id": "t1", "type": "pipeline", "priority": "high",
                "requester": "sys", "payload_redacted_hash": "h1", "reason_safe": "safe",
            }),
            _make_event(event_id=2, etype="control_room.task.updated", payload={
                "task_id": "t1", "status": "running", "started_ts": "2025-01-01T00:00:00Z",
            }),
            _make_event(event_id=3, etype="control_room.run.spawned", payload={
                "task_id": "t1", "run_id": "r1",
            }),
            _make_event(event_id=4, etype="control_room.approval.requested", payload={
                "approval_id": "a1", "task_id": "t1", "policy_id": "p1",
                "scope": "write", "run_id": "r1",
            }),
            _make_event(event_id=5, etype="control_room.approval.resolved", payload={
                "approval_id": "a1", "status": "approved", "resolved_by": "user:bob",
                "resolved_ts": "2025-01-01T01:00:00Z", "reason_safe": "ok",
            }),
            _make_event(event_id=6, etype="control_room.action.updated", payload={
                "action_id": "act1", "step_id": "s1", "name": "deploy",
                "tool": "kubectl", "status": "success", "order": 1,
                "args_redacted_hash": "ah1", "result_redacted_hash": "rh1",
            }),
        ]

        for ev in events:
            materialize_event(ev, graph=g)

        # Verify no node has raw content (long strings)
        for key, node in g.nodes.items():
            for field, value in node.items():
                if isinstance(value, str):
                    assert len(value) < 500, f"Graph node {key}.{field} has {len(value)} chars"
                    # No field should contain raw prompt/content keywords
                    assert "prompt" not in field.lower(), f"Field {key}.{field} might contain raw prompt data"
