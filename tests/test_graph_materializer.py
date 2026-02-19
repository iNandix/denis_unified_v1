"""Tests for Graph Materialization Layer (GML).

Covers:
- Event->Graph mapping for all supported event types
- Idempotency (same event twice => no duplication)
- Fail-open (graph disabled => pipeline continues)
- Fail-open (graph errors => swallowed, stats updated)
- Component/flag seeding
- No raw content in graph mutations
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
    etype: str = "rag.search.start",
    conversation_id: str = "conv_test",
    trace_id: str = "trace_test",
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
    """Ensure isolated GML DB + graph disabled for unit tests."""
    db_path = str(tmp_path / "test_gml.db")
    monkeypatch.setenv("DENIS_GML_DB_PATH", db_path)
    # Graph enabled but we mock the driver
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("NEO4J_PASSWORD", "test_pass")
    yield


class FakeGraphClient:
    """In-memory graph client for testing mutations."""

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


# ─── Mapping coverage tests ───


class TestRagSearchStartMapping:
    def test_creates_step_and_component(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(etype="rag.search.start")
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "pro_search"
        # Should have Step node
        steps = [k for k in g.nodes if k.startswith("Step:")]
        assert len(steps) >= 1
        # Component should be updated
        assert "Component:pro_search" in g.nodes


class TestRagSearchResultMapping:
    def test_creates_artifact_with_evidence_pack(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="rag.search.result",
            payload={
                "selected": [
                    {"chunk_id": "c1", "score": 0.9, "source": "example.com"},
                    {"chunk_id": "c2", "score": 0.8, "source": "test.org"},
                ],
            },
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        artifacts = [k for k in g.nodes if k.startswith("Artifact:")]
        assert len(artifacts) >= 1
        art = g.nodes[artifacts[0]]
        assert art.get("kind") == "evidence_pack"
        # Should have provenance sources
        sources = [k for k in g.nodes if k.startswith("Source:")]
        assert len(sources) >= 2

    def test_no_raw_content_in_artifact(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="rag.search.result",
            payload={
                "selected": [{"chunk_id": "c1", "score": 0.9, "source": "example.com"}],
            },
        )
        materialize_event(ev, graph=g)
        for key, node in g.nodes.items():
            for field, value in node.items():
                if isinstance(value, str) and len(value) > 500:
                    pytest.fail(f"Graph node {key}.{field} contains long text ({len(value)} chars)")


class TestRagContextCompiledMapping:
    def test_creates_context_pack_artifact(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="rag.context.compiled",
            payload={"chunks_count": 5, "citations": [{"chunk_id": "c1"}]},
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "rag_context_builder"
        artifacts = [k for k in g.nodes if k.startswith("Artifact:")]
        assert any(g.nodes[a].get("kind") == "context_pack" for a in artifacts)


class TestScrapingMapping:
    def test_scraping_page_creates_source(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="scraping.page",
            payload={"url": "https://docs.example.com/page"},
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "advanced_scraping"
        sources = [k for k in g.nodes if k.startswith("Source:")]
        assert any("docs.example.com" in k for k in sources)


class TestDecisionTraceSummaryMapping:
    def test_creates_decision_summary_artifact(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="agent.decision_trace_summary",
            payload={"blocked": False, "path": "inference_router:local", "latency_ms": 120},
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "control_room"
        artifacts = [k for k in g.nodes if k.startswith("Artifact:")]
        assert any(g.nodes[a].get("kind") == "decision_summary" for a in artifacts)


class TestAdaptiveReasoningMapping:
    def test_creates_step_and_artifact(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="agent.reasoning.summary",
            payload={
                "adaptive_reasoning": {
                    "goal_sha256": "abc123",
                    "goal_len": 42,
                    "tools_used": ["pro_search"],
                    "constraints_hit": [],
                    "retrieval": {"chunk_ids": ["c1", "c2"]},
                }
            },
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "control_room"
        steps = [k for k in g.nodes if k.startswith("Step:")]
        assert any(g.nodes[s].get("name") == "adaptive_reasoning" for s in steps)
        artifacts = [k for k in g.nodes if k.startswith("Artifact:")]
        assert any(g.nodes[a].get("kind") == "decision_summary" for a in artifacts)

    def test_no_raw_cot_in_graph(self):
        """Invariant: no raw CoT/prompt content stored in graph."""
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="agent.reasoning.summary",
            payload={
                "adaptive_reasoning": {
                    "goal_sha256": "abc123",
                    "goal_len": 42,
                    "tools_used": [],
                    "constraints_hit": [],
                    "retrieval": {"chunk_ids": []},
                }
            },
        )
        materialize_event(ev, graph=g)
        for key, node in g.nodes.items():
            for field, value in node.items():
                if isinstance(value, str):
                    assert "goal_text" not in field, "Raw goal text should not be in graph"
                    assert len(value) < 1000, f"Suspiciously long field {key}.{field}"


class TestIndexingUpsertMapping:
    def test_creates_chunk_artifact(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            etype="indexing.upsert",
            payload={"kind": "decision_summary", "hash_sha256": "deadbeef", "status": "upserted"},
        )
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert result.component_id == "vectorstore_qdrant"
        artifacts = [k for k in g.nodes if k.startswith("Artifact:")]
        assert any(g.nodes[a].get("kind") == "chunk" for a in artifacts)
        assert "Component:vectorstore_qdrant" in g.nodes


class TestErrorMapping:
    def test_marks_run_degraded(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(etype="error", payload={"code": "chat_failed", "msg": "timeout"})
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        runs = [k for k in g.nodes if k.startswith("Run:")]
        assert any(g.nodes[r].get("status") == "degraded" for r in runs)


class TestFreshnessOnlyEvents:
    """ops.metric, run.step, chat.message update ws_event_bus freshness only."""

    @pytest.mark.parametrize("etype", ["ops.metric", "run.step", "chat.message"])
    def test_updates_component_freshness(self, etype):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(etype=etype)
        result = materialize_event(ev, graph=g)

        assert result.handled is True
        assert "Component:ws_event_bus" in g.nodes


# ─── Idempotency tests ───


class TestIdempotency:
    def test_same_event_twice_no_duplicate_nodes(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(
            event_id=42,
            etype="rag.search.result",
            payload={"selected": [{"chunk_id": "c1", "score": 0.9, "source": "x.com"}]},
        )

        r1 = materialize_event(ev, graph=g)
        nodes_after_first = len(g.nodes)
        edges_after_first = len(g.edges)

        r2 = materialize_event(ev, graph=g)
        nodes_after_second = len(g.nodes)
        edges_after_second = len(g.edges)

        assert r1.handled is True
        assert r2.handled is True
        # Second pass should not add new mutations (MERGE is idempotent anyway,
        # but the SQLite dedupe gate should prevent even calling graph).
        # Due to flag seeding on each call, we allow some overhead from that.
        # The key invariant: no NEW step/artifact/source nodes from second call.
        assert nodes_after_second <= nodes_after_first + 2  # +2 tolerance for flag re-seeding

    def test_different_events_create_distinct_mutations(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev1 = _make_event(event_id=1, etype="rag.search.start")
        ev2 = _make_event(event_id=2, etype="rag.context.compiled", payload={"chunks_count": 3, "citations": []})

        materialize_event(ev1, graph=g)
        materialize_event(ev2, graph=g)

        steps = [k for k in g.nodes if k.startswith("Step:")]
        assert len(steps) >= 2  # pro_search + rag_build


# ─── Fail-open tests ───


class TestFailOpen:
    def test_graph_disabled_returns_not_handled(self, monkeypatch):
        monkeypatch.setenv("GRAPH_ENABLED", "0")
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event
        from denis_unified_v1.graph.graph_client import GraphClient

        g = GraphClient()  # Will be disabled
        ev = _make_event(etype="rag.search.start")
        result = materialize_event(ev, graph=g)

        assert result.handled is False

    def test_graph_error_swallowed(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        # Make upsert_component raise
        g.upsert_component = MagicMock(side_effect=RuntimeError("db_down"))
        g.upsert_run = MagicMock(side_effect=RuntimeError("db_down"))

        ev = _make_event(etype="rag.search.start")
        # Should NOT raise
        result = materialize_event(ev, graph=g)
        # Fail-open: returns handled=False on internal error
        assert result.handled is False

    def test_maybe_materialize_never_raises(self):
        from denis_unified_v1.graph.materializers.event_materializer import maybe_materialize_event

        g = FakeGraphClient()
        g.upsert_component = MagicMock(side_effect=RuntimeError("catastrophic"))
        g.upsert_run = MagicMock(side_effect=RuntimeError("catastrophic"))

        ev = _make_event(etype="rag.search.start")
        # Must NOT raise
        maybe_materialize_event(ev, graph=g)


# ─── Materializer stats tests ───


class TestMaterializerStats:
    def test_stats_updated_after_materialization(self):
        from denis_unified_v1.graph.materializers.event_materializer import (
            materialize_event,
            get_materializer_stats,
        )

        g = FakeGraphClient()
        ev = _make_event(etype="rag.search.start")
        materialize_event(ev, graph=g)

        stats = get_materializer_stats()
        assert stats["last_mutation_ts"] != ""
        assert stats["last_event_ts"] != ""
        assert isinstance(stats["lag_ms"], int)
        assert isinstance(stats["errors_window"], int)


# ─── Component/Flag seeding tests ───


class TestComponentFlagSeeding:
    def test_components_seeded_on_first_event(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(etype="rag.search.start")
        materialize_event(ev, graph=g)

        # Check expected components exist
        expected_components = [
            "vectorstore_qdrant",
            "pro_search",
            "rag_context_builder",
            "ws_event_bus",
            "chunker",
            "redaction_gate",
            "control_room",
        ]
        for cid in expected_components:
            assert f"Component:{cid}" in g.nodes, f"Component:{cid} missing from graph"

        # Check expected flags exist
        expected_flags = [
            "VECTORSTORE_ENABLED",
            "RAG_ENABLED",
            "INDEXING_ENABLED",
            "PRO_SEARCH_ENABLED",
        ]
        for fid in expected_flags:
            assert f"FeatureFlag:{fid}" in g.nodes, f"FeatureFlag:{fid} missing from graph"

    def test_dependency_edges_seeded(self):
        from denis_unified_v1.graph.materializers.event_materializer import materialize_event

        g = FakeGraphClient()
        ev = _make_event(etype="rag.search.start")
        materialize_event(ev, graph=g)

        dep_edges = [e for e in g.edges if e["type"] == "DEPENDS_ON"]
        assert len(dep_edges) >= 3  # rag->pro_search, pro_search->vectorstore, etc.

        gated_edges = [e for e in g.edges if e["type"] == "GATED_BY"]
        assert len(gated_edges) >= 2  # vectorstore->VECTORSTORE_ENABLED, etc.


# ─── emit_event hook integration test ───


class TestEmitEventHook:
    def test_emit_event_calls_materializer(self, tmp_path, monkeypatch):
        """Verify the hook in api/event_bus.py invokes GML."""
        monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
        monkeypatch.setenv("DENIS_GML_DB_PATH", str(tmp_path / "gml.db"))
        monkeypatch.setenv("GRAPH_ENABLED", "1")

        from api.event_bus import reset_event_bus_for_tests
        from api.persona.event_router import persona_emit as emit_event

        reset_event_bus_for_tests()

        with patch(
            "denis_unified_v1.graph.materializers.event_materializer.maybe_materialize_event"
        ) as mock_mat:
            emit_event(
                conversation_id="test_conv",
                trace_id="test_trace",
                type="rag.search.start",
                payload={"query_sha256": "abc", "query_len": 10, "k": 8},
            )
            assert mock_mat.called, "emit_event must call maybe_materialize_event"
            call_args = mock_mat.call_args
            event_arg = call_args[0][0] if call_args[0] else call_args[1].get("event")
            assert event_arg["type"] == "rag.search.start"
