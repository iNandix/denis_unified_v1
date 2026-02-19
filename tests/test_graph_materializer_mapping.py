from __future__ import annotations


class FakeGraph:
    def __init__(self):
        self.enabled = True
        self.components = []
        self.runs = []

    def upsert_feature_flag(self, **kwargs):
        return True

    def upsert_component(self, **kwargs):
        self.components.append(kwargs)
        return True

    def link_component_flag(self, **kwargs):
        return True

    def link_component_depends_on(self, **kwargs):
        return True

    def upsert_run(self, **kwargs):
        self.runs.append(kwargs)
        return True

    def upsert_step(self, **kwargs):
        return True

    def upsert_artifact(self, **kwargs):
        return True

    def upsert_source(self, **kwargs):
        return True

    def link_run_step(self, **kwargs):
        return True

    def link_step_artifact(self, **kwargs):
        return True

    def link_artifact_source(self, **kwargs):
        return True

    def link_run_provider(self, **kwargs):
        return True


def test_mapping_unknown_event_no_crash(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("DENIS_GML_DB_PATH", str(tmp_path / "gml.db"))

    from denis_unified_v1.graph.materializers.event_materializer import materialize_event

    g = FakeGraph()
    ev = {
        "event_id": 1,
        "ts": "2026-02-17T00:00:00Z",
        "conversation_id": "c1",
        "trace_id": "t1",
        "type": "chat.message",  # not materialized by v1 mappings
        "severity": "info",
        "schema_version": "1.0",
        "ui_hint": {"render": "x", "icon": "y"},
        "payload": {"role": "user", "content_sha256": "0" * 64, "content_len": 4},
    }
    res = materialize_event(ev, graph=g)
    assert res.handled is False
    # Still marks ws_event_bus freshness (component upsert)
    assert any(c.get("component_id") == "ws_event_bus" for c in g.components)


def test_mapping_rag_search_start_creates_run(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("DENIS_GML_DB_PATH", str(tmp_path / "gml.db"))

    from denis_unified_v1.graph.materializers.event_materializer import materialize_event

    g = FakeGraph()
    ev = {
        "event_id": 2,
        "ts": "2026-02-17T00:00:00Z",
        "conversation_id": "c2",
        "trace_id": "t2",
        "type": "rag.search.start",
        "severity": "info",
        "schema_version": "1.0",
        "ui_hint": {"render": "x", "icon": "y"},
        "payload": {"query_sha256": "0" * 64, "query_len": 4, "k": 8, "filters": None},
    }
    res = materialize_event(ev, graph=g)
    assert res.handled is True
    assert g.runs, "expected upsert_run"

